"""Tier mapping + persona + mock-loop tests (stdlib only — no external deps needed)."""

from __future__ import annotations

import asyncio
import unittest

from sam_worker.config import memory_turns_for_tier, model_for_tier
from sam_worker.personas import ALL, SAMUEL, SUB_AGENTS
from sam_worker.tier import TierState
from sam_worker.tools.rainmaker import TOOL_SCHEMA, MockRainmakerClient


class TierMapTests(unittest.TestCase):
    def test_model_routing_degrades_with_tier(self) -> None:
        self.assertEqual(model_for_tier(1), "hermes-full")
        self.assertEqual(model_for_tier(2), "gpt-4o-mini")
        self.assertEqual(model_for_tier(99), "gpt-4o-mini")  # safe default

    def test_memory_shrinks_with_tier(self) -> None:
        self.assertGreater(memory_turns_for_tier(1), memory_turns_for_tier(3))

    def test_tier_state_update_and_trim(self) -> None:
        st = TierState(tier=1)
        self.assertFalse(st.update(1))
        self.assertTrue(st.update(3))
        self.assertEqual(st.model, "gpt-4o-mini")
        history = [{"m": i} for i in range(40)]
        self.assertEqual(len(st.trim_history(history)), memory_turns_for_tier(3))

    def test_tier_clamped(self) -> None:
        st = TierState(tier=2)
        st.update(99)
        self.assertEqual(st.tier, 4)
        st.update(-5)
        self.assertEqual(st.tier, 0)


class PersonaTests(unittest.TestCase):
    def test_samuel_is_host_and_hidden_hermes(self) -> None:
        self.assertEqual(SAMUEL.id, "samuel")
        self.assertNotIn(SAMUEL.id, [p.id for p in SUB_AGENTS])
        self.assertIn("never mention hermes", SAMUEL.system_hint.lower())

    def test_samuel_canon_has_anti_hallucination_rules(self) -> None:
        """SAM-004: the canon prompt must explicitly fence the 2026-06-21 failures."""
        hint = SAMUEL.system_hint.lower()
        # Pricing/fees guardrail (invented $20-$100 trade fee + 0.5-1% AUM in prod).
        self.assertIn("pricing", hint)
        self.assertIn("fee", hint)
        # Never claim email/links/messaging delivery.
        self.assertIn("email", hint)
        # Never claim an onboarding team / other staff.
        self.assertIn("onboarding team", hint)
        # Never claim account state.
        self.assertIn("account", hint)
        # Must instruct honesty / "don't know" behavior.
        self.assertTrue("don't know" in hint or "i don't have" in hint or "say so" in hint)

    def test_samuel_canon_loaded_from_file(self) -> None:
        """The full canon (not just the inline fallback) should be in use."""
        self.assertGreater(len(SAMUEL.system_hint), 400)

    def test_all_personas_have_voice_env(self) -> None:
        for p in ALL.values():
            self.assertTrue(p.voice_env.endswith("_VOICE_ID"))


class RainmakerToolTests(unittest.TestCase):
    def test_write_tools_require_approval(self) -> None:
        for tool in TOOL_SCHEMA:
            if not tool.get("read_only", False):
                self.assertTrue(tool.get("requires_approval"), f"{tool['name']} must gate writes")

    def test_mock_client_shapes(self) -> None:
        rm = MockRainmakerClient()
        scans = asyncio.run(rm.get_scans(limit=1))
        self.assertTrue(scans["ok"])
        self.assertEqual(len(scans["scans"]), 1)


if __name__ == "__main__":
    unittest.main()
