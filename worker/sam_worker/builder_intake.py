"""Tool-only builder intake turns — one notebook, one visible gap at a time."""

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
_WAIT_FIELDS = {"research", "estimate"}
_WAIT_QIDS = {"_pending"}
_MIN_ANSWER_LEN = 3
_DUMP_HINTS = (
    "website",
    "producer",
    "project",
    "harbor",
    "menu",
    "reservation",
    "mobile",
    "app",
    "brand",
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
    if field and field not in {"research", "discovery", "estimate"}:
        form = sync.get("form_data") if isinstance(sync.get("form_data"), dict) else {}
        return bool(str(form.get(field) or "").strip())
    return False


def _is_wait_gap(gap: dict[str, Any]) -> bool:
    field = str(gap.get("field") or "")
    question_id = str(gap.get("questionId") or "")
    return field in _WAIT_FIELDS or question_id in _WAIT_QIDS


def _question_published(sync: dict[str, Any], question_id: str) -> bool:
    if not question_id or question_id in _WAIT_QIDS:
        return False
    questions = sync.get("questions") or []
    return any(isinstance(q, dict) and str(q.get("id") or "") == question_id for q in questions)


def _looks_like_dump(text: str, sync: dict[str, Any]) -> bool:
    cleaned = (text or "").strip()
    if len(cleaned) > 120:
        return True
    lower = cleaned.lower()
    hits = sum(1 for hint in _DUMP_HINTS if hint in lower)
    if hits >= 2 and len(cleaned) > 40:
        return True
    gaps = sync.get("gaps") or []
    gap = gaps[0] if gaps else {}
    field = str(gap.get("field") or "")
    if field == "discovery" and len(cleaned) > 80:
        return True
    return False


def _should_write_answer(text: str, sync: dict[str, Any], gap: dict[str, Any]) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or _looks_like_dump(cleaned, sync):
        return False
    if len(cleaned) < _MIN_ANSWER_LEN and not _LEAVE_RE.match(cleaned):
        return False
    if _gap_is_filled(sync, gap):
        return False

    field = str(gap.get("field") or "")
    question_id = str(gap.get("questionId") or "")
    focus = sync.get("focus") if isinstance(sync.get("focus"), dict) else {}
    focus_q = str(focus.get("questionId") or "")

    if focus_q and focus_q in _answered_ids(sync) and _LEAVE_RE.match(cleaned):
        return False

    if field == "discovery":
        if not question_id or question_id in _WAIT_QIDS:
            return False
        if not _question_published(sync, question_id):
            return False
        return question_id not in _answered_ids(sync)

    if field and field not in {"research", "discovery", "estimate", ""}:
        return not _gap_is_filled(sync, gap)

    return False


def _gap_spoken_text(gap_res: dict[str, Any]) -> str:
    gap = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
    if _is_wait_gap(gap):
        return _spoken_only(str(gap.get("question") or gap_res.get("text") or "")) or ""
    if gap_res.get("complete"):
        return _spoken_only(str(gap_res.get("text") or "")) or ""
    spoken = _spoken_only(str(gap_res.get("text") or ""))
    if gap.get("field") == "discovery" and gap.get("questionId") in _WAIT_QIDS:
        return ""
    if gap.get("field") == "discovery" and gap.get("questionId"):
        if not _question_published(gap_res, str(gap.get("questionId") or "")):
            return _spoken_only("One moment while I line up the next questions.") or ""
    return spoken or ""


async def run_builder_intake_turn(
    client: RainmakerClient,
    *,
    engagement_id: str,
    text: str,
) -> tuple[str, list[str]]:
    """Infer from context when possible; write only the visible unfilled gap."""
    cleaned = (text or "").strip()
    tools: list[str] = []
    if not cleaned or cleaned.startswith("[SYNC]"):
        return "", tools
    if len(cleaned) < _MIN_ANSWER_LEN and not _LEAVE_RE.match(cleaned):
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
        return _gap_spoken_text(gap_res) or "Done.", tools

    gap = gaps[0] if isinstance(gaps[0], dict) else {}
    if _is_wait_gap(gap):
        wait = str(gap.get("question") or "One moment.")
        return _spoken_only(wait) or wait, tools

    if str(gap.get("field") or "") == "discovery":
        qid = str(gap.get("questionId") or "")
        if qid and qid not in _WAIT_QIDS and not _question_published(sync, qid):
            wait = "One moment while I line up the next questions."
            return wait, tools

    wrote = False
    if _looks_like_dump(cleaned, sync):
        await client.run_tool(
            "proposal_apply_summary",
            {"engagement_id": engagement_id, "summary": cleaned},
        )
        tools.append("proposal_apply_summary")
        wrote = True
    elif _should_write_answer(cleaned, sync, gap):
        field = str(gap.get("field") or "")
        if field == "discovery":
            question_id = str(gap.get("questionId") or "")
            await client.run_tool(
                "proposal_answer_question",
                {"engagement_id": engagement_id, "question_id": question_id, "value": cleaned},
            )
            tools.append("proposal_answer_question")
            wrote = True
        elif field:
            await client.run_tool(
                "proposal_set_field",
                {"engagement_id": engagement_id, "field": field, "value": cleaned},
            )
            tools.append("proposal_set_field")
            wrote = True

    gap_res = await client.run_tool("proposal_ask_gap", {"engagement_id": engagement_id})
    tools.append("proposal_ask_gap")
    spoken = _gap_spoken_text(gap_res)
    if not spoken and wrote:
        spoken = "Got it."
    return spoken or ("Got it." if wrote else ""), tools
