# -*- coding: utf-8 -*-
"""SAM-034: tier session apply + payload parsing."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from livekit.agents import llm

from sam_worker.config import Settings, effective_model_for_tier
from sam_worker.tier import TierState
from sam_worker.tier_session import apply_tier_to_session, parse_tier_payload, trim_chat_context


class TierPayloadTests(unittest.TestCase):
    def test_parse_valid(self) -> None:
        self.assertEqual(parse_tier_payload({"type": "tier_update", "tier": 3}), 3)

    def test_parse_clamps(self) -> None:
        self.assertEqual(parse_tier_payload({"type": "tier_update", "tier": 99}), 4)

    def test_parse_rejects_wrong_type(self) -> None:
        self.assertIsNone(parse_tier_payload({"type": "text_input", "tier": 2}))


class EffectiveModelTests(unittest.TestCase):
    def test_openai_maps_hermes_placeholder(self) -> None:
        s = Settings(sam_brain="openai", openai_model="gpt-4o-mini")
        self.assertEqual(effective_model_for_tier(1, s), "gpt-4o-mini")

    def test_groq_uses_groq_model(self) -> None:
        s = Settings(sam_brain="groq", groq_model="llama-3.1-8b-instant")
        self.assertEqual(effective_model_for_tier(2, s), "llama-3.1-8b-instant")


class TrimChatContextTests(unittest.TestCase):
    def test_trim_keeps_last_turns(self) -> None:
        ctx = llm.ChatContext.empty()
        for i in range(10):
            ctx.add_message(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        removed = trim_chat_context(ctx, memory_turns=2)
        self.assertGreater(removed, 0)
        msgs = ctx.messages()
        self.assertLessEqual(len(msgs), 4)


class ApplyTierSessionTests(unittest.TestCase):
    def test_apply_updates_model_and_trims(self) -> None:
        ctx = llm.ChatContext.empty()
        for i in range(8):
            ctx.add_message(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        llm_inst = SimpleNamespace(_opts=SimpleNamespace(model="gpt-4o-mini"))
        session = SimpleNamespace(llm=llm_inst, history=ctx)
        settings = Settings(sam_brain="openai", openai_model="gpt-4o-mini")
        tier = TierState(tier=3)
        apply_tier_to_session(session, tier, settings)
        self.assertEqual(llm_inst._opts.model, "gpt-4o-mini")
        self.assertLessEqual(len(ctx.messages()), memory_turns_for_tier(3) * 2)


def memory_turns_for_tier(tier: int) -> int:
    from sam_worker.config import memory_turns_for_tier as m

    return m(tier)


if __name__ == "__main__":
    unittest.main()
