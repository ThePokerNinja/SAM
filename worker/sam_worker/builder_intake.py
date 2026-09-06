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
_FRAGMENT_AFFIRM_RE = re.compile(
    r"^(?:yeah|yep|yes|yup|ok(?:ay)?|sure|right|and|so|um+|uh+)\.?[\s,]*",
    re.I,
)
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
_FINALIZE_RE = re.compile(
    r"\b(yes|yep|yeah|send|finalize|looks good|go ahead|email it|confirm)\b",
    re.I,
)
_CONTINUE_RE = re.compile(r"\b(continue|resume|pick up|where were we)\b", re.I)
_WHAT_ELSE_RE = re.compile(r"what else should i know", re.I)
_SMS_FALLBACK = "I'll text you the link to finish the form."


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


def _active_discovery_gap(sync: dict[str, Any]) -> dict[str, Any]:
    gaps = sync.get("gaps") or []
    gap = gaps[0] if gaps else {}
    if not isinstance(gap, dict):
        return {}
    if str(gap.get("field") or "") != "discovery":
        return {}
    qid = str(gap.get("questionId") or "")
    if not qid or qid in _WAIT_QIDS:
        return {}
    return gap


def _is_stt_fragment(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or _LEAVE_RE.match(cleaned):
        return False
    if len(cleaned) >= 40:
        return False
    if _FRAGMENT_AFFIRM_RE.match(cleaned) and len(cleaned) < 28:
        return True
    words = [w for w in re.split(r"\s+", cleaned) if w]
    if len(words) <= 3 and len(cleaned) < 20:
        return True
    return False


def _merge_phone_answer(
    *,
    engagement_id: str,
    question_id: str,
    fragment: str,
    answer_buffer: dict[str, str] | None,
    is_phone: bool,
) -> tuple[str, bool]:
    """Return merged text and whether it is ready to write."""
    cleaned = (fragment or "").strip()
    if not is_phone or not question_id:
        return cleaned, bool(cleaned)
    key = f"{engagement_id}:{question_id}"
    prior = str((answer_buffer or {}).get(key) or "").strip()
    merged = f"{prior} {cleaned}".strip() if prior else cleaned
    if answer_buffer is not None:
        if _is_stt_fragment(cleaned) and not _answer_substantial(merged):
            answer_buffer[key] = merged
            return merged, False
        answer_buffer.pop(key, None)
    return merged, _answer_substantial(merged) or _LEAVE_RE.match(merged)


def _answer_substantial(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or _LEAVE_RE.match(cleaned):
        return True
    if len(cleaned) >= 24:
        return True
    words = [w for w in re.split(r"\s+", cleaned) if w]
    return len(words) >= 4


def _looks_like_dump(text: str, sync: dict[str, Any]) -> bool:
    cleaned = (text or "").strip()
    active = _active_discovery_gap(sync)
    if active:
        if len(cleaned) > 160:
            return True
        lower = cleaned.lower()
        hits = sum(1 for hint in _DUMP_HINTS if hint in lower)
        return hits >= 3 and len(cleaned) > 100
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


def _forbidden_spoken(text: str) -> bool:
    lower = (text or "").lower()
    if _WHAT_ELSE_RE.search(lower):
        return True
    if "hang on while i pull research" in lower:
        return True
    if "one second" in lower and "estimate" in lower:
        return True
    if "one moment while i line up the next questions" in lower:
        return True
    return False


def _track_spoken(
    engagement_id: str,
    spoken: str,
    *,
    last_spoken: dict[str, str] | None,
) -> str:
    cleaned = (spoken or "").strip()
    if not cleaned or not engagement_id:
        return cleaned
    prior = str((last_spoken or {}).get(engagement_id) or "").strip()
    if prior and prior == cleaned:
        return ""
    if last_spoken is not None:
        last_spoken[engagement_id] = cleaned
    return cleaned


def _gap_spoken_text(gap_res: dict[str, Any], *, sync: dict[str, Any] | None = None) -> str:
    gap = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
    if _is_wait_gap(gap):
        return _spoken_only(str(gap.get("question") or gap_res.get("text") or "")) or ""
    if gap_res.get("complete"):
        return _spoken_only(str(gap_res.get("text") or "")) or ""
    spoken = _spoken_only(str(gap_res.get("text") or ""))
    if gap.get("field") == "discovery" and gap.get("questionId") in _WAIT_QIDS:
        return ""
    if gap.get("field") == "discovery" and gap.get("questionId"):
        qid = str(gap.get("questionId") or "")
        published = _question_published(gap_res, qid) or (
            sync is not None and _question_published(sync, qid)
        )
        if not published:
            return spoken or _spoken_only(str(gap.get("question") or "")) or ""
    return spoken or ""


async def _ask_gap_spoken(
    client: RainmakerClient,
    *,
    engagement_id: str,
    tools: list[str],
    sync: dict[str, Any] | None = None,
    last_spoken: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    gap_res = await client.run_tool("proposal_ask_gap", {"engagement_id": engagement_id})
    tools.append("proposal_ask_gap")
    spoken = _gap_spoken_text(gap_res, sync=sync)
    if _forbidden_spoken(spoken):
        spoken = ""
    gap = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
    if spoken and gap.get("field") == "discovery" and gap.get("questionId") not in _WAIT_QIDS:
        spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken)
    if not spoken and gap_res.get("complete"):
        spoken = _track_spoken(
            engagement_id,
            _spoken_only(str(gap_res.get("text") or "")) or "",
            last_spoken=last_spoken,
        )
    return spoken, gap_res


async def run_builder_intake_turn(
    client: RainmakerClient,
    *,
    engagement_id: str,
    text: str,
    is_phone: bool = False,
    answer_buffer: dict[str, str] | None = None,
    last_spoken: dict[str, str] | None = None,
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
        if _CONTINUE_RE.search(cleaned):
            resume = await client.run_tool(
                "proposal_resume",
                {"engagement_id": engagement_id, "channel": "voice"},
            )
            tools.append("proposal_resume")
            return _spoken_only(str(resume.get("text") or "")) or "Picking up where we left off.", tools
        if _FINALIZE_RE.search(cleaned) and not _LEAVE_RE.match(cleaned):
            send = await client.run_tool("proposal_send", {"engagement_id": engagement_id})
            tools.append("proposal_send")
            spoken = _spoken_only(str(send.get("text") or "")) or "Sent."
            return spoken, tools
        base = _spoken_only(str(sync.get("text") or "")) or (
            "Intake is complete — tap the bar to edit."
        )
        if engagement_id and "Job id" not in base:
            base = f"{base} Job id {engagement_id}."
        return base, tools

    gaps = sync.get("gaps") or []
    if not gaps:
        spoken, _ = await _ask_gap_spoken(
            client,
            engagement_id=engagement_id,
            tools=tools,
            sync=sync,
            last_spoken=last_spoken,
        )
        return spoken or SMS_FALLBACK, tools

    gap = gaps[0] if isinstance(gaps[0], dict) else {}
    if _is_wait_gap(gap):
        field = str(gap.get("field") or "")
        if field == "research":
            await client.run_tool("proposal_research", {"engagement_id": engagement_id})
            tools.append("proposal_research")
            spoken, gap_res = await _ask_gap_spoken(
                client,
                engagement_id=engagement_id,
                tools=tools,
                sync=sync,
                last_spoken=last_spoken,
            )
            nxt = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
            if spoken and not _is_wait_gap(nxt):
                return spoken, tools
            return spoken or SMS_FALLBACK, tools
        if field == "estimate":
            est = await client.run_tool(
                "proposal_mark_estimate_ready",
                {"engagement_id": engagement_id},
            )
            tools.append("proposal_mark_estimate_ready")
            spoken = _spoken_only(str(est.get("text") or "")) or ""
            if _forbidden_spoken(spoken):
                spoken = ""
            if spoken:
                spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken)
            return spoken or SMS_FALLBACK, tools
        spoken, gap_res = await _ask_gap_spoken(
            client,
            engagement_id=engagement_id,
            tools=tools,
            sync=sync,
            last_spoken=last_spoken,
        )
        nxt = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
        if spoken and not _is_wait_gap(nxt):
            return spoken, tools
        return spoken or SMS_FALLBACK, tools

    if str(gap.get("field") or "") == "discovery":
        qid = str(gap.get("questionId") or "")
        if qid and qid not in _WAIT_QIDS and not _question_published(sync, qid):
            spoken = str(gap.get("question") or "")
            spoken = _spoken_only(spoken) or spoken
            if spoken and not _forbidden_spoken(spoken):
                spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken)
                if spoken:
                    return spoken, tools
            spoken, _ = await _ask_gap_spoken(
                client,
                engagement_id=engagement_id,
                tools=tools,
                sync=sync,
                last_spoken=last_spoken,
            )
            return spoken or SMS_FALLBACK, tools

    wrote = False
    answer_text = cleaned
    if str(gap.get("field") or "") == "discovery":
        qid = str(gap.get("questionId") or "")
        answer_text, ready = _merge_phone_answer(
            engagement_id=engagement_id,
            question_id=qid,
            fragment=cleaned,
            answer_buffer=answer_buffer,
            is_phone=is_phone,
        )
        if not ready:
            return "", tools

    if _looks_like_dump(answer_text, sync):
        await client.run_tool(
            "proposal_apply_summary",
            {"engagement_id": engagement_id, "summary": answer_text},
        )
        tools.append("proposal_apply_summary")
        wrote = True
    elif _should_write_answer(answer_text, sync, gap):
        field = str(gap.get("field") or "")
        if field == "discovery":
            question_id = str(gap.get("questionId") or "")
            await client.run_tool(
                "proposal_answer_question",
                {
                    "engagement_id": engagement_id,
                    "question_id": question_id,
                    "value": answer_text,
                },
            )
            tools.append("proposal_answer_question")
            wrote = True
        elif field:
            await client.run_tool(
                "proposal_set_field",
                {"engagement_id": engagement_id, "field": field, "value": answer_text},
            )
            tools.append("proposal_set_field")
            wrote = True

    spoken, _ = await _ask_gap_spoken(
        client,
        engagement_id=engagement_id,
        tools=tools,
        sync=sync,
        last_spoken=last_spoken,
    )
    if not spoken and wrote:
        spoken = "Got it."
    return spoken or ("Got it." if wrote else ""), tools
