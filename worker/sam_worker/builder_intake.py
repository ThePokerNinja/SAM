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
    r"\b(yes|yep|yeah|send|finalize|looks good|go ahead|confirm)\b",
    re.I,
)
_CONTINUE_RE = re.compile(r"\b(continue|resume|pick up|where were we)\b", re.I)
_WHAT_ELSE_RE = re.compile(r"what else should i know", re.I)
_EMAIL_RE = re.compile(r"\b(email|e-mail|mail it|inbox)\b", re.I)
_TEXT_RE = re.compile(r"\b(text|sms|message me|text me)\b", re.I)
_REVIEWED_RE = re.compile(
    r"\b(i (?:looked|reviewed|read|saw)|reviewed it|looks good|i'm good|im good|"
    r"no questions|approved|approve|yeah looks good)\b",
    re.I,
)
_CONFUSED_RE = re.compile(
    r"\b(i don'?t understand|don'?t get it|what do you mean|confused|huh|wait what|"
    r"that doesn'?t make sense|not sure what)\b",
    re.I,
)
_LOOKS_FINE_RE = re.compile(
    r"\b(looks good|looks fine|numbers look|that works|sounds good|good with|"
    r"ready to go|let'?s do it|ship it|approve|approved)\b",
    re.I,
)
_TOO_HIGH_RE = re.compile(
    r"\b(too (?:high|much|expensive)|lower|cheaper|cut|trim|reduce)\b",
    re.I,
)
_RECEIVED_RE = re.compile(
    r"\b(got it|received|i opened|opened it|opened the link|see it|got the text|got the email)\b",
    re.I,
)
_NO_QUESTIONS_RE = re.compile(
    r"\b(no questions|no more questions|all good|nothing else|we'?re good|that'?s it)\b",
    re.I,
)
_HANDOFF_RE = re.compile(
    r"\b(thank|thanks|all set|goodbye|bye)\b",
    re.I,
)
_BUDGET_RE = re.compile(
    r"\$\s*\d|\b(\d{1,3}(?:,\d{3})+|\d+)\s*(k|thousand|grand)?\b|\bbudget\b",
    re.I,
)
_BUDGET_WORDS_RE = re.compile(
    r"\b(fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|ten|eleven|twelve|"
    r"thirteen|fourteen|sixteen|seventeen|eighteen|nineteen|around|about)\b.*"
    r"\b(thousand|grand|k)\b|\bwe have about\b",
    re.I,
)
_COST_QUESTION_RE = re.compile(
    r"\b(how much|what(?:'s| is) (?:this|it) cost|price|pricing|what am i looking at)\b",
    re.I,
)
_AFFIRM_ONLY_RE = re.compile(
    r"^(yes|yep|yeah|yup|sure|ok|okay|do it|go ahead|sounds good|sounds right|"
    r"that works|please|perfect|please do|send it)\.?$",
    re.I,
)
_SMS_FALLBACK = "I'll text you the link to finish the form."
SMS_FALLBACK = _SMS_FALLBACK


def classify_close_turn(text: str, *, pending_offer: str, phase: str) -> str:
    """Map a close turn to intent given Samuel's last named offer — not magic verbs."""
    cleaned = (text or "").strip()
    low = cleaned.lower()
    if not cleaned:
        return "unclear"
    if _COST_QUESTION_RE.search(cleaned) and phase in {
        "context",
        "review_offered",
        "review_sent",
    }:
        return "cost_question"
    if _EMAIL_RE.search(cleaned) or "inbox" in low or "send it to my email" in low:
        return "choose_email"
    if _TEXT_RE.search(cleaned) or "just text" in low:
        return "choose_text"
    if _CONTINUE_RE.search(cleaned):
        return "continue"
    if phase == "closed":
        if _HANDOFF_RE.search(cleaned):
            return "closed_ack"
        return "closed"
    if pending_offer == "confirm_received" and _RECEIVED_RE.search(cleaned):
        return "received_link"
    if pending_offer == "any_questions" and _NO_QUESTIONS_RE.search(cleaned):
        return "no_more_questions"
    if pending_offer in {"any_questions", "approve_bid"} and _LOOKS_FINE_RE.search(cleaned):
        return "approve_bid"
    if pending_offer == "workshop_bid":
        if _CONFUSED_RE.search(cleaned):
            return "confused"
        if _TOO_HIGH_RE.search(cleaned) or (
            _BUDGET_RE.search(cleaned) and re.search(r"\b(lower|less|under|around|about)\b", low)
        ):
            return "named_lower"
        if _BUDGET_RE.search(cleaned) or _BUDGET_WORDS_RE.search(cleaned):
            if re.search(r"\b(more|higher|extra|add|expand)\b", low):
                return "named_higher"
            return "named_lower"
        if _LOOKS_FINE_RE.search(cleaned):
            return "look_fine"
    if _REVIEWED_RE.search(cleaned) or re.search(
        r"\b(i looked|looked at|read it)\b", cleaned, re.I
    ):
        return "reviewed"
    if phase in {"workshop", "budget", "phase1_approved"} and (
        _BUDGET_RE.search(cleaned) or _BUDGET_WORDS_RE.search(cleaned)
    ):
        if re.search(r"\b(more|higher|extra|add|expand)\b", low):
            return "named_higher"
        return "named_lower"
    if _AFFIRM_ONLY_RE.match(cleaned.strip()):
        return "affirm" if pending_offer else "affirm_no_offer"
    if re.search(r"\bsend it\b", cleaned, re.I) and pending_offer in {
        "send_final",
        "choose_email",
        "choose_text",
        "send_draft",
        "mark_reviewed",
        "workshop_bid",
        "lock_bid",
    }:
        return "affirm"
    return "unclear"


def _pack_hint(sync: dict[str, Any]) -> str:
    pack = sync.get("packMatch") if isinstance(sync.get("packMatch"), dict) else {}
    name = str(pack.get("name") or pack.get("label") or pack.get("id") or "").strip()
    if not name or pack.get("unmatched"):
        return ""
    return name.replace("-", " ").replace("_", " ")


def _reflect_answer(answer: str) -> str:
    """Half-sentence SPIN reflect before the next discovery question."""
    cleaned = (answer or "").strip()
    if not cleaned or _LEAVE_RE.match(cleaned):
        return ""
    words = [w for w in re.split(r"\s+", cleaned) if w]
    if len(words) < 3:
        return ""
    snippet = " ".join(words[:8])
    if len(snippet) > 52:
        snippet = snippet[:49].rsplit(" ", 1)[0] + "..."
    return f"Got it — {snippet}. "


def _closer_discovery_line(answer: str, question: str) -> str:
    reflect = _reflect_answer(answer)
    q = (question or "").strip()
    if reflect and q:
        return f"{reflect}{q}"
    return q or reflect.strip()


def _offer_prompt(conf: float, *, pack_hint: str = "") -> str:
    lead = f"This looks like a {pack_hint} job. " if pack_hint else ""
    return (
        f"{lead}I'm about {conf:.0f}% confident on the scope. "
        "I can send the draft by email or text — which do you want?"
    )


def _draft_sent_prompt(channel: str) -> str:
    return f"Draft is on the way by {channel}. Tell me when you've looked it over."


def _workshop_prompt() -> str:
    return (
        "Thanks for looking. How do those hours and dollars look — "
        "anything feel high, or ready to adjust scope?"
    )


def _confused_prompt() -> str:
    return (
        "The total is hours times our blended rate — we can trim optional tasks or add polish. "
        "What would you cut first, or does the total feel about right?"
    )


def _final_offer_prompt() -> str:
    return "Want me to send the final estimate and text the notebook link?"


def _confirm_received_prompt() -> str:
    return "Did you get the text or email, and were you able to open the notebook link?"


def _any_questions_prompt() -> str:
    return "Any last questions on scope, timeline, or the number before we wrap?"


def _handoff_line() -> str:
    return "Thank you — you're all set. A sales associate will follow up within 24 hours."


def _budget_prompt() -> str:
    return _workshop_prompt()


def _restate_pending(sales: dict[str, Any], *, sync: dict[str, Any] | None = None) -> str:
    prompt = str(sales.get("pendingPrompt") or "").strip()
    if prompt:
        return prompt
    phase = str(sales.get("phase") or "context")
    try:
        conf = float(sales.get("confidence") or (sync or {}).get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if phase in {"review_offered", "context"} and conf >= 85:
        return _offer_prompt(conf, pack_hint=_pack_hint(sync or {}))
    if phase == "review_sent":
        return "Tell me when you've looked at the draft."
    if phase in {"reviewed", "workshop", "phase1_approved"}:
        return _workshop_prompt()
    if phase == "budget":
        if sales.get("budgetBand"):
            return _final_offer_prompt()
        return _workshop_prompt()
    if phase == "closed":
        return _handoff_line()
    if pending_offer == "confirm_received":
        return _confirm_received_prompt()
    if pending_offer == "any_questions":
        return _any_questions_prompt()
    return _offer_prompt(conf, pack_hint=_pack_hint(sync or {})) if conf >= 85 else (
        "I still need more of the actual job before I send a draft — "
        "what has to ship on the site?"
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


def _sales_from(sync: dict[str, Any]) -> dict[str, Any]:
    raw = sync.get("sales")
    return dict(raw) if isinstance(raw, dict) else {}


def _confidence_offer_line(sync: dict[str, Any], sales: dict[str, Any] | None = None) -> str:
    state = sales or _sales_from(sync)
    try:
        conf = float(state.get("confidence") or sync.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf >= 85:
        return _offer_prompt(conf, pack_hint=_pack_hint(sync))
    return (
        "I still need more of the actual job before I send a draft — "
        "what has to ship on the site?"
    )


async def _set_pending_offer(
    client: RainmakerClient,
    *,
    engagement_id: str,
    offer: str,
    prompt: str,
    tools: list[str],
) -> None:
    await client.run_tool(
        "proposal_sales_set_pending",
        {
            "engagement_id": engagement_id,
            "pendingOffer": offer,
            "pendingPrompt": prompt,
        },
    )
    tools.append("proposal_sales_set_pending")


async def _send_draft_by_channel(
    client: RainmakerClient,
    *,
    engagement_id: str,
    channel: str,
    sync: dict[str, Any],
    sales: dict[str, Any],
    tools: list[str],
) -> str:
    phase = str(sales.get("phase") or "context")
    try:
        conf = float(sales.get("confidence") or sync.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if phase in {"context", "review_offered"} and conf < 85 and phase != "review_offered":
        return _confidence_offer_line(sync, sales)
    if phase in {"context", "review_offered"}:
        chosen = await _advance_sales(
            client,
            engagement_id=engagement_id,
            event="choose_channel",
            tools=tools,
            channel=channel,
        )
        if not chosen.get("ok"):
            line = _spoken_only(str(chosen.get("text") or "")) or _offer_prompt(
                conf, pack_hint=_pack_hint(sync)
            )
            await _set_pending_offer(
                client,
                engagement_id=engagement_id,
                offer="choose_channel",
                prompt=line,
                tools=tools,
            )
            return line
    sent = await _send_proposal(
        client,
        engagement_id=engagement_id,
        kind="draft",
        tools=tools,
        channel=channel,
    )
    if not sent.get("ok"):
        line = _confidence_offer_line(sync, sales)
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="choose_channel",
            prompt=line,
            tools=tools,
        )
        return line
    line = _draft_sent_prompt(channel)
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="mark_reviewed",
        prompt=line,
        tools=tools,
    )
    return line


async def _mark_reviewed_and_workshop(
    client: RainmakerClient,
    *,
    engagement_id: str,
    sales: dict[str, Any],
    tools: list[str],
    last_spoken: dict[str, str] | None = None,
) -> str:
    phase = str(sales.get("phase") or "context")
    if phase == "review_sent":
        marked = await _advance_sales(
            client,
            engagement_id=engagement_id,
            event="mark_reviewed",
            tools=tools,
        )
        if not marked.get("ok"):
            line = _spoken_only(str(marked.get("text") or "")) or "Did you get a chance to look at the draft?"
            await _set_pending_offer(
                client,
                engagement_id=engagement_id,
                offer="mark_reviewed",
                prompt=line,
                tools=tools,
            )
            return line
        line = _spoken_only(str(marked.get("text") or "")) or _workshop_prompt()
    elif phase in {"workshop", "reviewed", "budget"}:
        line = str(sales.get("pendingPrompt") or _workshop_prompt())
    else:
        line = "Did you get a chance to look at the draft?"
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="mark_reviewed",
            prompt=line,
            tools=tools,
        )
        return line
    line = _track_spoken(engagement_id, line, last_spoken=last_spoken) or line
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="workshop_bid",
        prompt=line,
        tools=tools,
    )
    return line


async def _lock_bid_and_offer_final(
    client: RainmakerClient,
    *,
    engagement_id: str,
    tools: list[str],
    mode: str = "accept",
    budget: str = "",
) -> str:
    extra: dict[str, Any] = {"mode": mode}
    if budget:
        extra["budgetBand"] = budget[:120]
    locked = await _advance_sales(
        client,
        engagement_id=engagement_id,
        event="lock_bid",
        tools=tools,
        **extra,
    )
    if not locked.get("ok"):
        line = _spoken_only(str(locked.get("text") or "")) or _workshop_prompt()
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="workshop_bid",
            prompt=line,
            tools=tools,
        )
        return line
    line = _final_offer_prompt()
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="send_final",
        prompt=line,
        tools=tools,
    )
    return line


async def _workshop_named_target(
    client: RainmakerClient,
    *,
    engagement_id: str,
    budget: str,
    tools: list[str],
    intent: str,
) -> str:
    await _advance_sales(
        client,
        engagement_id=engagement_id,
        event="set_budget",
        tools=tools,
        budgetBand=budget[:120],
    )
    mode = "expand" if intent == "named_higher" else "cut"
    if intent == "named_higher":
        line = (
            f"Got it — I'll add hours toward {budget[:40]}. "
            "Where should the extra time go — polish, timeline, or another feature?"
        )
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="lock_bid",
            prompt=line,
            tools=tools,
        )
        return line
    line = (
        f"I can trim optional tasks to land near {budget[:40]}. "
        "Want me to lock that revised bid?"
    )
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="lock_bid",
        prompt=line,
        tools=tools,
    )
    return line


async def _confirm_received(
    client: RainmakerClient,
    *,
    engagement_id: str,
    tools: list[str],
) -> str:
    advanced = await _advance_sales(
        client,
        engagement_id=engagement_id,
        event="confirm_opened",
        tools=tools,
    )
    line = _spoken_only(str(advanced.get("text") or "")) or _any_questions_prompt()
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="any_questions",
        prompt=line,
        tools=tools,
    )
    return line


async def _close_with_handoff(
    client: RainmakerClient,
    *,
    engagement_id: str,
    tools: list[str],
) -> str:
    await _advance_sales(
        client,
        engagement_id=engagement_id,
        event="approve_close",
        tools=tools,
    )
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="",
        prompt="",
        tools=tools,
    )
    return _handoff_line()


async def _send_final_estimate(
    client: RainmakerClient,
    *,
    engagement_id: str,
    tools: list[str],
) -> str:
    approved = await _advance_sales(
        client,
        engagement_id=engagement_id,
        event="approve_phase2",
        tools=tools,
    )
    if not approved.get("ok"):
        line = _spoken_only(str(approved.get("text") or "")) or _final_offer_prompt()
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="send_final",
            prompt=line,
            tools=tools,
        )
        return line
    sent = await _send_proposal(
        client, engagement_id=engagement_id, kind="final", tools=tools
    )
    if not sent.get("ok"):
        line = _spoken_only(str(sent.get("text") or "")) or "I couldn't send the final estimate."
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="send_final",
            prompt=line,
            tools=tools,
        )
        return line
    line = _confirm_received_prompt()
    await _set_pending_offer(
        client,
        engagement_id=engagement_id,
        offer="confirm_received",
        prompt=line,
        tools=tools,
    )
    return f"Done — final estimate sent. {line}"


async def _advance_sales(
    client: RainmakerClient,
    *,
    engagement_id: str,
    event: str,
    tools: list[str],
    **extra: Any,
) -> dict[str, Any]:
    args = {"engagement_id": engagement_id, "event": event, **extra}
    result = await client.run_tool("proposal_sales_advance", args)
    tools.append("proposal_sales_advance")
    return result


async def _send_proposal(
    client: RainmakerClient,
    *,
    engagement_id: str,
    kind: str,
    tools: list[str],
    channel: str = "",
) -> dict[str, Any]:
    args: dict[str, Any] = {"engagement_id": engagement_id, "kind": kind}
    if channel:
        args["channel"] = channel
    result = await client.run_tool("proposal_send", args)
    tools.append("proposal_send")
    return result


async def _handle_sales_close(
    client: RainmakerClient,
    *,
    engagement_id: str,
    text: str,
    sync: dict[str, Any],
    tools: list[str],
    last_spoken: dict[str, str] | None = None,
) -> str:
    """Last-offer confirmations: affirm fires only the pending named move."""
    cleaned = (text or "").strip()
    sales = _sales_from(sync)
    phase = str(sales.get("phase") or "context")
    pending_offer = str(sales.get("pendingOffer") or "")
    try:
        conf = float(sales.get("confidence") or sync.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0

    if phase == "closed":
        return _handoff_line()

    intent = classify_close_turn(cleaned, pending_offer=pending_offer, phase=phase)

    if intent == "continue":
        resume = await client.run_tool(
            "proposal_resume",
            {"engagement_id": engagement_id, "channel": "voice"},
        )
        tools.append("proposal_resume")
        return _spoken_only(str(resume.get("text") or "")) or "Picking up where we left off."

    if intent == "cost_question":
        alt = _confused_prompt() if pending_offer == "workshop_bid" else _restate_pending(sales, sync=sync)
        alt = _track_spoken(engagement_id, alt, last_spoken=last_spoken) or alt
        if pending_offer == "workshop_bid":
            await _set_pending_offer(
                client,
                engagement_id=engagement_id,
                offer="workshop_bid",
                prompt=alt,
                tools=tools,
            )
        return alt

    if intent == "choose_email":
        return await _send_draft_by_channel(
            client,
            engagement_id=engagement_id,
            channel="email",
            sync=sync,
            sales=sales,
            tools=tools,
        )

    if intent == "choose_text":
        return await _send_draft_by_channel(
            client,
            engagement_id=engagement_id,
            channel="text",
            sync=sync,
            sales=sales,
            tools=tools,
        )

    if intent == "reviewed":
        return await _mark_reviewed_and_workshop(
            client,
            engagement_id=engagement_id,
            sales=sales,
            tools=tools,
            last_spoken=last_spoken,
        )

    if intent == "confused":
        line = _track_spoken(engagement_id, _confused_prompt(), last_spoken=last_spoken)
        if not line:
            return ""
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="workshop_bid",
            prompt=line,
            tools=tools,
        )
        return line

    if intent in {"named_lower", "named_higher"}:
        return await _workshop_named_target(
            client,
            engagement_id=engagement_id,
            budget=cleaned,
            tools=tools,
            intent=intent,
        )

    if intent == "look_fine":
        return await _lock_bid_and_offer_final(
            client, engagement_id=engagement_id, tools=tools, mode="accept"
        )

    if intent == "received_link":
        return await _confirm_received(client, engagement_id=engagement_id, tools=tools)

    if intent in {"no_more_questions", "approve_bid", "closed_ack"}:
        return await _close_with_handoff(client, engagement_id=engagement_id, tools=tools)

    if intent == "affirm":
        if pending_offer == "choose_channel":
            return _restate_pending(sales, sync=sync)
        if pending_offer in {"choose_email", "send_draft"}:
            return await _send_draft_by_channel(
                client,
                engagement_id=engagement_id,
                channel="email",
                sync=sync,
                sales=sales,
                tools=tools,
            )
        if pending_offer == "choose_text":
            return await _send_draft_by_channel(
                client,
                engagement_id=engagement_id,
                channel="text",
                sync=sync,
                sales=sales,
                tools=tools,
            )
        if pending_offer == "mark_reviewed":
            return await _mark_reviewed_and_workshop(
                client,
                engagement_id=engagement_id,
                sales=sales,
                tools=tools,
                last_spoken=last_spoken,
            )
        if pending_offer in {"workshop_bid", "ask_budget"}:
            alt = _track_spoken(engagement_id, _confused_prompt(), last_spoken=last_spoken)
            if not alt:
                return ""
            await _set_pending_offer(
                client,
                engagement_id=engagement_id,
                offer="workshop_bid",
                prompt=alt,
                tools=tools,
            )
            return alt
        if pending_offer == "lock_bid":
            return await _lock_bid_and_offer_final(
                client, engagement_id=engagement_id, tools=tools, mode="cut"
            )
        if pending_offer == "send_final":
            return await _send_final_estimate(
                client, engagement_id=engagement_id, tools=tools
            )
        if pending_offer == "confirm_received":
            return await _confirm_received(client, engagement_id=engagement_id, tools=tools)
        if pending_offer == "any_questions":
            return await _close_with_handoff(client, engagement_id=engagement_id, tools=tools)

    if intent in {"affirm_no_offer", "unclear"}:
        if pending_offer or phase in {
            "review_offered",
            "review_sent",
            "reviewed",
            "workshop",
            "budget",
            "phase1_approved",
            "phase2_approved",
        }:
            alt = _restate_pending(sales, sync=sync)
            if pending_offer == "workshop_bid":
                alt = _track_spoken(engagement_id, alt, last_spoken=last_spoken)
                if not alt:
                    alt = _confused_prompt()
                    alt = _track_spoken(engagement_id, alt, last_spoken=last_spoken) or alt
                    await _set_pending_offer(
                        client,
                        engagement_id=engagement_id,
                        offer="workshop_bid",
                        prompt=alt,
                        tools=tools,
                    )
                    return alt
            return alt or _confused_prompt()

    if conf >= 85 or phase == "review_offered":
        offered = await _advance_sales(
            client,
            engagement_id=engagement_id,
            event="offer_review",
            tools=tools,
        )
        if offered.get("ok"):
            line = _spoken_only(str(offered.get("text") or "")) or _confidence_offer_line(
                offered, offered.get("sales") if isinstance(offered.get("sales"), dict) else sales
            )
            await _set_pending_offer(
                client,
                engagement_id=engagement_id,
                offer="choose_channel",
                prompt=line,
                tools=tools,
            )
            return line
        line = _confidence_offer_line(sync, sales)
        await _set_pending_offer(
            client,
            engagement_id=engagement_id,
            offer="choose_channel",
            prompt=line,
            tools=tools,
        )
        return line

    return _confidence_offer_line(sync, sales)


async def run_builder_intake_turn(
    client: RainmakerClient,
    *,
    engagement_id: str,
    text: str,
    is_phone: bool = False,
    answer_buffer: dict[str, str] | None = None,
    last_spoken: dict[str, str] | None = None,
    speak: bool = True,
) -> tuple[str, list[str]]:
    """Infer from context when possible; write only the visible unfilled gap."""
    cleaned = (text or "").strip()
    tools: list[str] = []

    def _out(spoken: str) -> tuple[str, list[str]]:
        return (spoken if speak else ""), tools

    if not cleaned or cleaned.startswith("[SYNC]"):
        return _out("")
    if len(cleaned) < _MIN_ANSWER_LEN and not _LEAVE_RE.match(cleaned):
        return _out("")

    sync = await client.get_intake_sync(engagement_id)
    if not sync.get("ok"):
        return _out("I lost the form session." if speak else "")

    if not sync.get("complete") and _COST_QUESTION_RE.search(cleaned):
        if not speak:
            return _out("")
        gaps = sync.get("gaps") or []
        active = gaps[0] if gaps and isinstance(gaps[0], dict) else {}
        if active and not _is_wait_gap(active):
            q = _spoken_only(str(active.get("question") or "")) or str(active.get("question") or "")
            line = f"I'll get you a real number once I understand the job — {q}".strip(" —")
            line = _track_spoken(engagement_id, line, last_spoken=last_spoken) or line
            return _out(line)
        line = (
            "I'll get you a real number once I understand the job — "
            "what's the main thing that has to work on day one?"
        )
        return _out(line)

    if sync.get("complete"):
        spoken = await _handle_sales_close(
            client,
            engagement_id=engagement_id,
            text=cleaned,
            sync=sync,
            tools=tools,
            last_spoken=last_spoken,
        )
        if not speak and "proposal_resume" not in tools and "proposal_send" not in tools:
            spoken = ""
        return (spoken or ""), tools

    gaps = sync.get("gaps") or []
    if not gaps:
        spoken, _ = await _ask_gap_spoken(
            client,
            engagement_id=engagement_id,
            tools=tools,
            sync=sync,
            last_spoken=last_spoken,
        )
        return _out(spoken or (SMS_FALLBACK if speak else ""))

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
                return _out(spoken)
            return _out(spoken or (SMS_FALLBACK if speak else ""))
        if field == "estimate":
            await client.run_tool(
                "proposal_mark_estimate_ready",
                {"engagement_id": engagement_id},
            )
            tools.append("proposal_mark_estimate_ready")
            if speak:
                offered = await _advance_sales(
                    client,
                    engagement_id=engagement_id,
                    event="offer_review",
                    tools=tools,
                )
                if offered.get("ok"):
                    spoken = _spoken_only(str(offered.get("text") or "")) or _confidence_offer_line(
                        offered, offered.get("sales") if isinstance(offered.get("sales"), dict) else None
                    )
                    await _set_pending_offer(
                        client,
                        engagement_id=engagement_id,
                        offer="choose_channel",
                        prompt=spoken,
                        tools=tools,
                    )
                    spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken)
                    return _out(spoken or SMS_FALLBACK)
            return _out("")
        spoken, gap_res = await _ask_gap_spoken(
            client,
            engagement_id=engagement_id,
            tools=tools,
            sync=sync,
            last_spoken=last_spoken,
        )
        nxt = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
        if spoken and not _is_wait_gap(nxt):
            return _out(spoken)
        return _out(spoken or (SMS_FALLBACK if speak else ""))

    if str(gap.get("field") or "") == "discovery":
        qid = str(gap.get("questionId") or "")
        if qid and qid not in _WAIT_QIDS and not _question_published(sync, qid):
            spoken = str(gap.get("question") or "")
            spoken = _spoken_only(spoken) or spoken
            if spoken and not _forbidden_spoken(spoken):
                spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken)
                if spoken:
                    return _out(spoken)
            spoken, _ = await _ask_gap_spoken(
                client,
                engagement_id=engagement_id,
                tools=tools,
                sync=sync,
                last_spoken=last_spoken,
            )
            return _out(spoken or (SMS_FALLBACK if speak else ""))

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
            return _out("")

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

    spoken, gap_res = await _ask_gap_spoken(
        client,
        engagement_id=engagement_id,
        tools=tools,
        sync=sync,
        last_spoken=last_spoken,
    )
    if wrote and answer_text and spoken and speak:
        nxt_gap = gap_res.get("gap") if isinstance(gap_res.get("gap"), dict) else {}
        if str(nxt_gap.get("field") or "") == "discovery":
            spoken = _closer_discovery_line(answer_text, spoken)
            spoken = _track_spoken(engagement_id, spoken, last_spoken=last_spoken) or spoken
    if not spoken and wrote and speak:
        spoken = "Got it."
    return _out(spoken or ("Got it." if wrote and speak else ""))
