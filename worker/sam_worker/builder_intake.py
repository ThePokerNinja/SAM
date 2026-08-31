"""Tool-only builder intake turns after the first dump (answer/set_field then ask_gap)."""

from __future__ import annotations

import re
from typing import Any

from .tools.handlers import _spoken_only
from .tools.rainmaker import RainmakerClient

_LEAVE_RE = re.compile(
    r"^(?:leave it|looks good|that's fine|that is fine|keep it|no change|no changes|"
    r"don't change|do not change|nah|nope|skip)\.?$",
    re.I,
)


def _answered_ids(sync: dict[str, Any]) -> set[str]:
    rows = sync.get("answers") or []
    return {
        str(row.get("questionId") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("value") or "").strip()
    }


def _gap_is_filled(sync: dict[str, Any], gap: dict[str, Any]) -> bool:
    field = str(gap.get("field") or "")
    question_id = str(gap.get("questionId") or "")
    if field == "discovery" and question_id:
        return question_id in _answered_ids(sync)
    if field and field not in {"research", "discovery"}:
        form = sync.get("form_data") if isinstance(sync.get("form_data"), dict) else {}
        return bool(str(form.get(field) or "").strip())
    return False


async def run_builder_intake_turn(
    client: RainmakerClient,
    *,
    engagement_id: str,
    text: str,
) -> tuple[str, list[str]]:
    """Write the current gap from user speech/chat, then ask the next gap."""
    cleaned = (text or "").strip()
    tools: list[str] = []
    if not cleaned or cleaned.startswith("[SYNC]"):
        return "", tools

    sync = await client.get_intake_sync(engagement_id)
    if not sync.get("ok"):
        return "I lost the form session.", tools
    if sync.get("complete"):
        return _spoken_only(str(sync.get("text") or "Intake is complete — tap the bar to edit.")) or (
            "Intake is complete — tap the bar to edit."
        ), tools

    gaps = sync.get("gaps") or []
    if not gaps:
        gap_res = await client.run_tool("proposal_ask_gap", {"engagement_id": engagement_id})
        tools.append("proposal_ask_gap")
        return _spoken_only(str(gap_res.get("text") or "")) or "Done.", tools

    gap = gaps[0] if isinstance(gaps[0], dict) else {}
    focus = sync.get("focus") if isinstance(sync.get("focus"), dict) else {}
    answered = _answered_ids(sync)
    focus_q = str(focus.get("questionId") or "")
    wrote = False

    if focus_q and focus_q in answered and _LEAVE_RE.match(cleaned):
        pass
    elif focus_q and focus_q in answered:
        await client.run_tool(
            "proposal_answer_question",
            {"engagement_id": engagement_id, "question_id": focus_q, "value": cleaned},
        )
        tools.append("proposal_answer_question")
        wrote = True
    elif str(gap.get("field") or "") == "discovery":
        question_id = str(gap.get("questionId") or "")
        if question_id and question_id != "_pending" and question_id not in answered:
            await client.run_tool(
                "proposal_answer_question",
                {"engagement_id": engagement_id, "question_id": question_id, "value": cleaned},
            )
            tools.append("proposal_answer_question")
            wrote = True
    elif str(gap.get("field") or "") not in {"research", "discovery", ""}:
        field = str(gap.get("field") or "")
        if not _gap_is_filled(sync, gap):
            await client.run_tool(
                "proposal_set_field",
                {"engagement_id": engagement_id, "field": field, "value": cleaned},
            )
            tools.append("proposal_set_field")
            wrote = True

    gap_res = await client.run_tool("proposal_ask_gap", {"engagement_id": engagement_id})
    tools.append("proposal_ask_gap")
    spoken = _spoken_only(str(gap_res.get("text") or ""))
    if not spoken and wrote:
        spoken = "Got it."
    return spoken or "Done.", tools
