"""SAM-006: function-tool handlers format rm_api data and degrade honestly on failure."""

from __future__ import annotations

import asyncio
import unittest

from sam_worker.config import Settings
from sam_worker.tools.handlers import (
    build_rainmaker_client,
    handle_get_pulse,
    handle_get_research,
    handle_get_scans,
    handle_get_trades,
    handle_queue_research,
    handle_run_scan,
)
from sam_worker.tools.rainmaker import HttpRainmakerClient, MockRainmakerClient


class SpyClient:
    """Records that a tool actually called through to the client (AC: mock invoked)."""

    def __init__(self, scans=None, pulse=None, trades=None, run=None, queue=None, research=None) -> None:
        self.calls: list[str] = []
        self._scans = scans or {"ok": True, "symbols": ["NVDA", "AAPL"], "newSymbols": ["AAPL"]}
        self._pulse = pulse or {"ok": True, "available": True, "label": "Risk-on", "pct": 62, "confidence": "med"}
        self._trades = trades or {"ok": True, "status": "closed", "trades": [{"symbol": "NVDA", "entry": 100, "exit": 110, "qty": 5}]}
        self._run = run or {"ok": True, "newSymbols": ["TSLA"], "count": 9}
        self._queue = queue or {"ok": True, "shortId": "abc12345", "status": "queued", "queuedAhead": 0}
        self._research = research or {"ok": True, "items": [{"prompt": "p", "summary": "Solid setup on NVDA"}], "count": 1}

    async def get_scans(self, limit: int = 10) -> dict:
        self.calls.append(f"get_scans:{limit}")
        return self._scans

    async def get_pulse(self) -> dict:
        self.calls.append("get_pulse")
        return self._pulse

    async def get_trades(self, status=None) -> dict:
        self.calls.append(f"get_trades:{status}")
        return self._trades

    async def run_scan(self) -> dict:
        self.calls.append("run_scan")
        return self._run

    async def queue_research(self, prompt: str) -> dict:
        self.calls.append(f"queue_research:{prompt}")
        return self._queue

    async def get_research(self, limit: int = 3) -> dict:
        self.calls.append(f"get_research:{limit}")
        return self._research


class HandlerInvokeTests(unittest.TestCase):
    def test_scans_handler_invokes_client_and_formats(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_get_scans(spy, limit=2))
        self.assertIn("get_scans:2", spy.calls)
        self.assertIn("NVDA", out)
        self.assertIn("New today", out)

    def test_pulse_handler_invokes_client_and_formats(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_get_pulse(spy))
        self.assertIn("get_pulse", spy.calls)
        self.assertIn("Risk-on", out)
        self.assertIn("62", out)

    def test_trades_handler_invokes_client_and_formats(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_get_trades(spy))
        self.assertIn("get_trades:None", spy.calls)
        self.assertIn("NVDA", out)
        self.assertIn("+$50", out)


class TriggerHandlerTests(unittest.TestCase):
    def test_run_scan_reports_new_symbols(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_run_scan(spy))
        self.assertIn("run_scan", spy.calls)
        self.assertIn("TSLA", out)

    def test_run_scan_no_new(self) -> None:
        spy = SpyClient(run={"ok": True, "newSymbols": [], "count": 5})
        out = asyncio.run(handle_run_scan(spy))
        self.assertIn("5", out)

    def test_run_scan_failure_is_honest(self) -> None:
        spy = SpyClient(run={"ok": False, "error": "http_401"})
        out = asyncio.run(handle_run_scan(spy))
        self.assertIn("couldn't", out.lower())

    def test_queue_research_acks(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_queue_research(spy, "NVDA float and short interest"))
        self.assertTrue(any(c.startswith("queue_research:") for c in spy.calls))
        self.assertIn("queued", out.lower())

    def test_queue_research_rejects_too_short(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_queue_research(spy, "x"))
        # Must not call through on a too-short prompt.
        self.assertFalse(any(c.startswith("queue_research:") for c in spy.calls))
        self.assertIn("more", out.lower())

    def test_get_research_reads_summaries(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_get_research(spy))
        self.assertIn("get_research:3", spy.calls)
        self.assertIn("NVDA", out)

    def test_get_research_empty(self) -> None:
        spy = SpyClient(research={"ok": True, "items": [], "count": 0})
        out = asyncio.run(handle_get_research(spy))
        self.assertIn("empty", out.lower())


class HandlerDegradeTests(unittest.TestCase):
    def test_scans_failure_is_honest(self) -> None:
        spy = SpyClient(scans={"ok": False, "error": "timeout"})
        out = asyncio.run(handle_get_scans(spy))
        self.assertIn("couldn't", out.lower())
        self.assertIn("won't guess", out.lower())

    def test_pulse_unavailable_message(self) -> None:
        spy = SpyClient(pulse={"ok": True, "available": False, "note": "closed"})
        out = asyncio.run(handle_get_pulse(spy))
        self.assertIn("no morning bias", out.lower())

    def test_trades_empty_message(self) -> None:
        spy = SpyClient(trades={"ok": True, "status": "closed", "trades": []})
        out = asyncio.run(handle_get_trades(spy))
        self.assertIn("no recorded trades", out.lower())

    def test_open_status_note_passthrough(self) -> None:
        spy = SpyClient(trades={"ok": True, "status": "open", "trades": [], "note": "n/a"})
        # empty short-circuits before note; non-empty carries the note
        spy2 = SpyClient(trades={
            "ok": True, "status": "open",
            "trades": [{"symbol": "NVDA", "entry": 1, "exit": 2, "qty": 1}],
            "note": "Realized only.",
        })
        out = asyncio.run(handle_get_trades(spy2, status="open"))
        self.assertIn("Realized only.", out)


class MockFormattingTests(unittest.TestCase):
    """Handlers must also format the MockRainmakerClient shapes (offline/dev)."""

    def test_mock_scans(self) -> None:
        out = asyncio.run(handle_get_scans(MockRainmakerClient()))
        self.assertIn("NVDA", out)

    def test_mock_pulse(self) -> None:
        out = asyncio.run(handle_get_pulse(MockRainmakerClient()))
        self.assertIn("risk-on", out.lower())


class ClientFactoryTests(unittest.TestCase):
    def test_mock_when_flag_set(self) -> None:
        s = Settings(sam_mock_rm=True, rm_api_base_url="https://x")
        self.assertIsInstance(build_rainmaker_client(s), MockRainmakerClient)

    def test_mock_when_no_base_url(self) -> None:
        s = Settings(sam_mock_rm=False, rm_api_base_url="")
        self.assertIsInstance(build_rainmaker_client(s), MockRainmakerClient)

    def test_http_when_configured(self) -> None:
        s = Settings(sam_mock_rm=False, rm_api_base_url="https://x", rm_api_token="t")
        self.assertIsInstance(build_rainmaker_client(s), HttpRainmakerClient)


if __name__ == "__main__":
    unittest.main()
