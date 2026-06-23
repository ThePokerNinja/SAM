"""SAM-005: HttpRainmakerClient read-only rm_api integration (offline via MockTransport)."""

from __future__ import annotations

import asyncio
import unittest

import httpx

from sam_worker.tools.rainmaker import HttpRainmakerClient

BASE = "https://rm-api.test"
TOKEN = "cron-secret"


def _client(handler) -> HttpRainmakerClient:
    transport = httpx.MockTransport(handler)
    ac = httpx.AsyncClient(transport=transport)
    return HttpRainmakerClient(BASE, TOKEN, client=ac)


class GetScansTests(unittest.TestCase):
    def test_parses_symbols_and_caps_limit(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("X-RM-CRON-TOKEN")
            return httpx.Response(
                200,
                json={
                    "at": 1718000000,
                    "symbols": ["NVDA", "AAPL", "MSFT", "AMD"],
                    "newSymbols": ["AMD"],
                },
            )

        res = asyncio.run(_client(handler).get_scans(limit=2))
        self.assertTrue(res["ok"])
        self.assertEqual(res["symbols"], ["NVDA", "AAPL"])
        self.assertEqual(res["newSymbols"], ["AMD"])
        self.assertEqual(res["count"], 4)
        self.assertTrue(captured["url"].endswith("/scan/latest"))
        self.assertEqual(captured["auth"], TOKEN)

    def test_empty_scan_payload(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"at": None, "symbols": [], "newSymbols": []})

        res = asyncio.run(_client(handler).get_scans())
        self.assertTrue(res["ok"])
        self.assertEqual(res["symbols"], [])
        self.assertEqual(res["count"], 0)


class GetPulseTests(unittest.TestCase):
    def test_parses_morning_bias(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "at": 1718000000,
                    "source": "rm_api",
                    "market": {
                        "score": 0.3,
                        "pct": 62,
                        "label": "Risk-on",
                        "confidence": "medium",
                        "drivers": ["breadth"],
                    },
                    "narrowTape": False,
                    "conflict": False,
                },
            )

        res = asyncio.run(_client(handler).get_pulse())
        self.assertTrue(res["ok"])
        self.assertTrue(res["available"])
        self.assertEqual(res["label"], "Risk-on")
        self.assertEqual(res["pct"], 62)
        self.assertEqual(res["confidence"], "medium")
        self.assertIn("futures=0", captured["url"])

    def test_null_bias_is_unavailable_not_error(self) -> None:
        # rm_api returns ``MorningBias | None`` -> a literal JSON ``null`` body.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})

        res = asyncio.run(_client(handler).get_pulse())
        self.assertTrue(res["ok"])
        self.assertFalse(res["available"])
        self.assertIn("note", res)


class GetTradesTests(unittest.TestCase):
    def test_parses_round_trips(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("X-RM-CRON-TOKEN")
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "roundTrips": [
                        {"symbol": "NVDA", "entry": 100, "exit": 110, "qty": 5},
                    ],
                    "fills": 4,
                    "rawFillCount": 4,
                },
            )

        res = asyncio.run(_client(handler).get_trades())
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "closed")
        self.assertEqual(res["count"], 1)
        self.assertTrue(captured["url"].endswith("/trade/round-trips"))
        self.assertEqual(captured["auth"], TOKEN)

    def test_open_status_adds_note(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": True, "roundTrips": []})

        res = asyncio.run(_client(handler).get_trades(status="open"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "open")
        self.assertIn("note", res)


class RunScanTests(unittest.TestCase):
    def test_posts_and_parses_new_symbols(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("X-RM-CRON-TOKEN")
            return httpx.Response(200, json={"ok": True, "newSymbols": ["NVDA", "AMD"], "count": 7})

        res = asyncio.run(_client(handler).run_scan())
        self.assertTrue(res["ok"])
        self.assertEqual(res["newSymbols"], ["NVDA", "AMD"])
        self.assertEqual(res["count"], 7)
        self.assertEqual(captured["method"], "POST")
        self.assertTrue(captured["url"].endswith("/scan/scheduled"))
        self.assertEqual(captured["auth"], TOKEN)

    def test_run_scan_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Invalid cron token"})

        res = asyncio.run(_client(handler).run_scan())
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "http_401")


class QueueResearchTests(unittest.TestCase):
    def test_posts_prompt_and_parses_id(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["body"] = request.content
            return httpx.Response(
                200,
                json={"ok": True, "id": "abcd1234-ef", "short_id": "abcd1234", "status": "queued", "queued_ahead": 2},
            )

        res = asyncio.run(_client(handler).queue_research("research NVDA float"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["shortId"], "abcd1234")
        self.assertEqual(res["status"], "queued")
        self.assertEqual(res["queuedAhead"], 2)
        self.assertEqual(captured["method"], "POST")
        self.assertTrue(captured["url"].endswith("/research/ideas"))
        self.assertIn(b"research NVDA float", captured["body"])


class GetResearchTests(unittest.TestCase):
    def test_parses_digest(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "research_digest": [
                        {"id": "1", "prompt": "p1", "summary": "s1"},
                        {"id": "2", "prompt": "p2", "summary": "s2"},
                    ],
                },
            )

        res = asyncio.run(_client(handler).get_research(limit=3))
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["items"][0]["summary"], "s1")
        self.assertIn("limit=3", captured["url"])


class FailureModeTests(unittest.TestCase):
    def test_http_error_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        res = asyncio.run(_client(handler).get_scans())
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "http_500")

    def test_unauthorized_surfaces_as_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Authentication required"})

        res = asyncio.run(_client(handler).get_trades())
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "http_401")

    def test_timeout_is_structured(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("slow", request=request)

        res = asyncio.run(_client(handler).get_pulse())
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "timeout")

    def test_bad_json_is_structured(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json", headers={"content-type": "application/json"})

        res = asyncio.run(_client(handler).get_scans())
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "bad_json")

    def test_no_token_omits_header(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["has_auth"] = "X-RM-CRON-TOKEN" in request.headers
            return httpx.Response(200, json={"symbols": []})

        transport = httpx.MockTransport(handler)
        ac = httpx.AsyncClient(transport=transport)
        client = HttpRainmakerClient(BASE, "", client=ac)
        asyncio.run(client.get_scans())
        self.assertFalse(captured["has_auth"])


if __name__ == "__main__":
    unittest.main()
