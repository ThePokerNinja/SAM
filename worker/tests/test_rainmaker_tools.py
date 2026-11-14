"""SAM-006: function-tool handlers format rm_api data and degrade honestly on failure."""

from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from sam_worker.config import Settings
from sam_worker.tools.handlers import (
    build_rainmaker_client,
    handle_get_brief,
    handle_get_pulse,
    handle_get_research,
    handle_get_scans,
    handle_get_trades,
    handle_list_studio_runs,
    handle_make_studio_deliverable,
    handle_queue_research,
    handle_run_scan,
    handle_send_brief,
    handle_send_hero,
)
from sam_worker.tools.rainmaker import HttpRainmakerClient, MockRainmakerClient
from sam_worker.tools.rainmaker_registry import _OWNER_REFUSAL, register_rainmaker_tools
from sam_worker.tools.registry import ToolRegistry

STUDIO_BASE = "https://rm-api.test"
STUDIO_TOKEN = "cron-secret"


class SpyClient:
    """Records that a tool actually called through to the client (AC: mock invoked)."""

    def __init__(self, scans=None, pulse=None, trades=None, run=None, queue=None, research=None, brief=None, send_brief_res=None, send_hero_res=None) -> None:
        self.calls: list[str] = []
        self._scans = scans or {"ok": True, "symbols": ["NVDA", "AAPL"], "newSymbols": ["AAPL"]}
        self._pulse = pulse or {"ok": True, "available": True, "label": "Risk-on", "pct": 62, "confidence": "med"}
        self._trades = trades or {"ok": True, "status": "closed", "trades": [{"symbol": "NVDA", "entry": 100, "exit": 110, "qty": 5}]}
        self._run = run or {"ok": True, "newSymbols": ["TSLA"], "count": 9}
        self._queue = queue or {"ok": True, "shortId": "abc12345", "status": "queued", "queuedAhead": 0}
        self._research = research or {"ok": True, "items": [{"prompt": "p", "summary": "Solid setup on NVDA"}], "count": 1}
        self._brief = brief or {"ok": True, "message": "Good morning. Top 3: scans, workout, review."}
        self._send_brief_res = send_brief_res or {"ok": True, "sent": True}
        self._send_hero_res = send_hero_res or {"ok": True, "sent": True}

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

    async def get_brief(self) -> dict:
        self.calls.append("get_brief")
        return self._brief

    async def send_brief(self) -> dict:
        self.calls.append("send_brief")
        return self._send_brief_res

    async def send_hero(self) -> dict:
        self.calls.append("send_hero")
        return self._send_hero_res

    async def list_studio_runs(self, limit: int = 8) -> dict:
        self.calls.append(f"list_studio_runs:{limit}")
        return {"ok": True, "runs": [{"id": "pov-01", "name": "pov-01"}]}

    async def make_studio_deliverable(self, type: str, run_id: str = "") -> dict:
        self.calls.append(f"make:{type}")
        return {"ok": True, "asset": {"id": f"{type}-1", "type": type, "status": "draft"}}


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


class BriefHeroHandlerTests(unittest.TestCase):
    def test_get_brief_reads_message(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_get_brief(spy))
        self.assertIn("get_brief", spy.calls)
        self.assertIn("Good morning", out)

    def test_send_brief_confirms(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_send_brief(spy))
        self.assertIn("send_brief", spy.calls)
        self.assertIn("texted", out.lower())

    def test_send_hero_confirms(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_send_hero(spy))
        self.assertIn("send_hero", spy.calls)
        self.assertIn("hero", out.lower())


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


class StudioHandlerTests(unittest.TestCase):
    def test_list_runs(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_list_studio_runs(spy))
        self.assertIn("list_studio_runs", spy.calls[0])
        self.assertIn("pov-01", out)

    def test_make(self) -> None:
        spy = SpyClient()
        out = asyncio.run(handle_make_studio_deliverable(spy, "email"))
        self.assertIn("make:email", spy.calls)
        self.assertIn("email", out.lower())


class StudioVoiceToolTests(unittest.TestCase):
    """Studio voice tools end to end: registry tool -> handler -> HttpRainmakerClient -> rm_api."""

    def setUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.registry = ToolRegistry()
        register_rainmaker_tools(self.registry)

    def _tool(self, name: str, routes: dict[tuple[str, str], dict], *, owner: bool = True):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            body = routes.get((request.method, request.url.path))
            if body is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=body)

        client = HttpRainmakerClient(
            STUDIO_BASE,
            STUDIO_TOKEN,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        tools = self.registry.build_livekit_tools(
            client,
            lambda: owner,
            function_tool=lambda fn: fn,
            owner_refusal="owner only",
            only=[name],
        )
        return tools[0]

    def _only_request(self) -> httpx.Request:
        self.assertEqual(len(self.requests), 1)
        req = self.requests[0]
        self.assertEqual(req.headers.get("X-RM-CRON-TOKEN"), STUDIO_TOKEN)
        return req

    def test_registered_with_tiers(self) -> None:
        specs = {s.name: s for s in self.registry.specs()}
        for name in ("list_studio_runs", "studio_asset_status", "studio_campaign_report"):
            self.assertTrue(specs[name].read_only, name)
        for name in ("make_studio_deliverable", "record_studio_publish"):
            self.assertFalse(specs[name].read_only, name)
            self.assertIn("Owner only", specs[name].description)

    def test_list_studio_runs(self) -> None:
        tool = self._tool(
            "list_studio_runs",
            {("GET", "/studio/runs"): {"ok": True, "runs": [{"id": "r1", "name": "pov-01"}, {"id": "r2", "name": "safari"}]}},
            owner=False,
        )
        out = asyncio.run(tool(None))
        req = self._only_request()
        self.assertEqual(req.url.params.get("limit"), "8")
        self.assertEqual(out, "Studio runs: pov-01, safari.")

    def test_studio_asset_status(self) -> None:
        tool = self._tool(
            "studio_asset_status",
            {("GET", "/studio/asset/email-r1"): {"ok": True, "asset": {"id": "email-r1", "status": "draft", "cost_usd": 0.12}}},
            owner=False,
        )
        out = asyncio.run(tool(None, "email-r1"))
        self._only_request()
        self.assertEqual(out, "Asset email-r1: draft, $0.12.")

    def test_studio_campaign_report(self) -> None:
        tool = self._tool(
            "studio_campaign_report",
            {
                ("GET", "/studio/campaign/report"): {
                    "ok": True,
                    "run": {"id": "r1", "name": "pov-01"},
                    "assets": [{"id": "a"}, {"id": "b"}],
                    "cost_usd": 1.5,
                }
            },
            owner=False,
        )
        out = asyncio.run(tool(None, "r1"))
        req = self._only_request()
        self.assertEqual(req.url.params.get("run_id"), "r1")
        self.assertEqual(out, "Report pov-01: 2 assets, $1.50.")

    def test_read_tool_failure_is_honest(self) -> None:
        tool = self._tool("studio_asset_status", {}, owner=False)
        out = asyncio.run(tool(None, "missing"))
        self.assertIn("couldn't pull the asset status", out)

    def test_make_studio_deliverable_owner(self) -> None:
        tool = self._tool(
            "make_studio_deliverable",
            {("POST", "/studio/make"): {"ok": True, "asset": {"id": "email-r1", "type": "email", "status": "draft"}, "run_id": "r1"}},
        )
        out = asyncio.run(tool(None, "email", "r1"))
        req = self._only_request()
        self.assertEqual(json.loads(req.content), {"type": "email", "run_id": "r1"})
        self.assertEqual(out, "Drafted email as email-r1. Open Studio to review.")

    def test_make_studio_deliverable_paid_step_pauses(self) -> None:
        tool = self._tool(
            "make_studio_deliverable",
            {("POST", "/studio/make"): {"ok": False, "needs_approval": True, "reason": "paid step $2.00 exceeds $0 render gate"}},
        )
        out = asyncio.run(tool(None, "video"))
        req = self._only_request()
        self.assertEqual(json.loads(req.content), {"type": "video"})
        self.assertEqual(out, "Make paused: paid step $2.00 exceeds $0 render gate.")

    def test_record_studio_publish_owner(self) -> None:
        tool = self._tool(
            "record_studio_publish",
            {("POST", "/studio/publish"): {"ok": True, "publish": {"asset_id": "email-r1", "url": "https://x.test/p", "channel": "web"}}},
        )
        out = asyncio.run(tool(None, "email-r1", "https://x.test/p"))
        req = self._only_request()
        self.assertEqual(json.loads(req.content), {"asset_id": "email-r1", "url": "https://x.test/p"})
        self.assertEqual(out, "Recorded publish for email-r1.")

    def test_make_studio_deliverable_refuses_non_owner(self) -> None:
        tool = self._tool("make_studio_deliverable", {("POST", "/studio/make"): {"ok": True}}, owner=False)
        out = asyncio.run(tool(None, "email", "r1"))
        self.assertEqual(out, _OWNER_REFUSAL)
        self.assertEqual(self.requests, [])

    def test_record_studio_publish_refuses_non_owner(self) -> None:
        tool = self._tool("record_studio_publish", {("POST", "/studio/publish"): {"ok": True}}, owner=False)
        out = asyncio.run(tool(None, "email-r1", "https://x.test/p"))
        self.assertEqual(out, _OWNER_REFUSAL)
        self.assertEqual(self.requests, [])


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
