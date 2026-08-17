# -*- coding: utf-8 -*-
"""SAM-034: apply TierState to a live AgentSession (model + memory trim)."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import llm

from .config import Settings, effective_model_for_tier
from .prompt_budget import estimate_tokens
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


def _item_text(item: Any) -> str:
    text = getattr(item, "text_content", None)
    if text:
        return str(text)
    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            else:
                parts.append(str(getattr(part, "text", part) or ""))
        return " ".join(p for p in parts if p)
    return str(content or "")


def trim_chat_context_tokens(chat_ctx: Any, token_cap: int) -> int:
    """Drop oldest non-system messages until history fits ``token_cap``.

    Always keeps the latest item so the current user turn cannot disappear.
    """
    if token_cap <= 0:
        return 0
    items = list(getattr(chat_ctx, "items", []) or [])
    if not items:
        return 0
    pinned: list[Any] = []
    rest: list[Any] = []
    for item in items:
        role = getattr(item, "role", None)
        if getattr(item, "type", "message") == "message" and role in {"system", "developer"}:
            pinned.append(item)
        else:
            rest.append(item)
    if not rest:
        return 0
    kept: list[Any] = []
    used = 0
    for index, item in enumerate(reversed(rest)):
        tokens = estimate_tokens(_item_text(item))
        if kept and used + tokens > token_cap:
            continue
        kept.append(item)
        used += tokens
        if index == 0 and used > token_cap:
            # Latest turn alone exceeds the cap; keep it anyway.
            break
    kept.reverse()
    new_items = pinned + kept
    removed = len(items) - len(new_items)
    if removed:
        chat_ctx.items = new_items
    return removed


def apply_tier_to_session(session: Any, tier_state: TierState, settings: Settings) -> None:
    """Apply brain model + memory depth at a turn boundary (never mid-utterance)."""
    model = effective_model_for_tier(tier_state.tier, settings)
    llm_inst = session.llm
    if llm_inst is not None and hasattr(llm_inst, "_opts"):
        llm_inst._opts.model = model

    removed = trim_chat_context(session.history, tier_state.memory_turns)
    token_removed = trim_chat_context_tokens(
        session.history, getattr(settings, "history_token_cap", 0) or 0
    )
    _log.info(
        "tier applied: tier=%d model=%s memory_turns=%d trimmed_items=%d token_trimmed=%d",
        tier_state.tier,
        model,
        tier_state.memory_turns,
        removed,
        token_removed,
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
