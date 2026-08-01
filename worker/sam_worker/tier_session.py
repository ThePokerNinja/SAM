# -*- coding: utf-8 -*-
"""SAM-034: apply TierState to a live AgentSession (model + memory trim)."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import llm

from .config import Settings, effective_model_for_tier
from .tier import TierState

_log = logging.getLogger("sam.tier")


def trim_chat_context(chat_ctx: llm.ChatContext, memory_turns: int) -> int:
    """Trim history to the last N user/assistant turns (ADR-7). Returns removed item count."""
    if memory_turns <= 0:
        return 0
    items = chat_ctx.items
    if not items:
        return 0

    msg_budget = memory_turns * 2
    split_idx = len(items)
    msg_count = 0
    for i in range(len(items) - 1, -1, -1):
        item = items[i]
        if item.type == "message" and item.role in ("user", "assistant"):
            msg_count += 1
            if msg_count >= msg_budget:
                split_idx = i
                break

    if split_idx <= 0:
        return 0

    removed = split_idx
    chat_ctx.items = items[split_idx:]
    return removed


def apply_tier_to_session(session: Any, tier_state: TierState, settings: Settings) -> None:
    """Apply brain model + memory depth at a turn boundary (never mid-utterance)."""
    model = effective_model_for_tier(tier_state.tier, settings)
    llm_inst = session.llm
    if llm_inst is not None and hasattr(llm_inst, "_opts"):
        llm_inst._opts.model = model

    removed = trim_chat_context(session.history, tier_state.memory_turns)
    _log.info(
        "tier applied: tier=%d model=%s memory_turns=%d trimmed_items=%d",
        tier_state.tier,
        model,
        tier_state.memory_turns,
        removed,
    )


def parse_tier_payload(payload: dict) -> int | None:
    """Parse a client tier_update message. Returns tier id or None."""
    if payload.get("type") != "tier_update":
        return None
    try:
        tier = int(payload.get("tier"))
    except (TypeError, ValueError):
        return None
    return max(0, min(4, tier))
