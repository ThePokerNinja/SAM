# -*- coding: utf-8 -*-
"""SAM-008: live integration test - voice worker tools against prod rm_api.

Run manually (never in CI unless SAM_INTEGRATION=1):

    SAM_INTEGRATION=1 python -m pytest tests/test_integration_prod.py -v

Requires:
    RM_API_TOKEN     - same value as RM_CRON_TOKEN on the rainmaker-api Render service.
    RM_API_BASE_URL  - optional, defaults to prod URL.

Skips automatically when SAM_INTEGRATION is unset so the suite stays offline-safe.
"""

from __future__ import annotations

import asyncio
import os
import unittest

SKIP_REASON = "Set SAM_INTEGRATION=1 to run live prod tests (requires RM_API_TOKEN)."
_SKIP = os.environ.get("SAM_INTEGRATION", "").strip() not in {"1", "true", "yes"}

BASE_URL = os.environ.get(
    "RM_API_BASE_URL", "https://rainmaker-api-waqs.onrender.com"
).rstrip("/")
TOKEN = os.environ.get("RM_API_TOKEN", "")


def _client():
    from sam_worker.tools.rainmaker import HttpRainmakerClient

    return HttpRainmakerClient(BASE_URL, TOKEN, timeout=20.0)


# ---------------------------------------------------------------------------
# Client layer -- raw HTTP + response parsing
# ---------------------------------------------------------------------------


@unittest.skipIf(_SKIP, SKIP_REASON)
class ProdClientTests(unittest.TestCase):
    """Verify HttpRainmakerClient parses real rm_api responses correctly."""

    def test_get_scans_ok(self) -> None:
        res = asyncio.run(_client().get_scans(limit=5))
        self.assertTrue(res.get("ok"), f"get_scans failed: {res}")
        self.assertIn("symbols", res)
        self.assertIsInstance(res["symbols"], list)
        self.assertIn("count", res)
        print(f"\n  [scan] {res['count']} symbols, top={res['symbols'][:3]}")

    def test_get_pulse_ok(self) -> None:
        res = asyncio.run(_client().get_pulse())
        self.assertTrue(res.get("ok"), f"get_pulse failed: {res}")
        self.assertIn("available", res)
        if res["available"]:
            self.assertIn("label", res)
            self.assertIn("pct", res)
            print(
                f"\n  [pulse] {res.get('label')} {res.get('pct')}%"
                f" conf={res.get('confidence')}"
            )
        else:
            print("\n  [pulse] unavailable (market closed / no bias posted yet)")

    def test_get_trades_ok_with_token(self) -> None:
        """Authenticated round-trips endpoint -- 401 means RM_API_TOKEN is wrong."""
        if not TOKEN:
            self.skipTest("RM_API_TOKEN not set -- skipping authenticated trade route.")
        res = asyncio.run(_client().get_trades())
        self.assertTrue(
            res.get("ok"),
            f"get_trades returned error (check RM_API_TOKEN matches RM_CRON_TOKEN): {res}",
        )
        self.assertIn("trades", res)
        self.assertIn("count", res)
        print(f"\n  [trades] {res['count']} round-trips")

    def test_get_trades_fails_cleanly_without_token(self) -> None:
        """Without a token the endpoint returns 401 -- verify graceful degradation."""
        from sam_worker.tools.rainmaker import HttpRainmakerClient

        client = HttpRainmakerClient(BASE_URL, "", timeout=20.0)
        res = asyncio.run(client.get_trades())
        # rm_api returns 401 when RM_CRON_TOKEN is configured and the header is missing.
        # If rm_api has no token configured (dev), it returns 200 -- both are acceptable.
        if res.get("ok"):
            print("\n  [trades-noauth] rm_api has no token gate (dev mode) -- ok")
        else:
            self.assertIn("error", res)
            self.assertIn("401", res["error"])
            print(f"\n  [trades-noauth] 401 as expected: {res['error']}")


# ---------------------------------------------------------------------------
# Handler layer -- spoken output from the real data
# ---------------------------------------------------------------------------


@unittest.skipIf(_SKIP, SKIP_REASON)
class ProdHandlerTests(unittest.TestCase):
    """Verify the handle_* grounding layer produces valid spoken strings from prod data."""

    def test_handle_get_scans_is_speakable(self) -> None:
        from sam_worker.tools.handlers import handle_get_scans

        text = asyncio.run(handle_get_scans(_client(), limit=5))
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 5)
        print(f"\n  [handle_scans] {text!r}")

    def test_handle_get_pulse_is_speakable(self) -> None:
        from sam_worker.tools.handlers import handle_get_pulse

        text = asyncio.run(handle_get_pulse(_client()))
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 5)
        print(f"\n  [handle_pulse] {text!r}")

    def test_handle_get_trades_is_speakable(self) -> None:
        from sam_worker.tools.handlers import handle_get_trades

        text = asyncio.run(handle_get_trades(_client()))
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 5)
        # Must be real data or an honest "couldn't pull" -- never invented numbers.
        print(f"\n  [handle_trades] {text!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
