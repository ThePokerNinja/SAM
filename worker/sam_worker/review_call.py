"""Owner review call for Charles's Proposal Studio.

rm_api's SMS keyword ``REVIEW`` dials the owner through ``/dial`` with
``brief="review: <digest>"`` and ``spoken="review"``. The worker treats that
outbound leg as an owner session (tools on, owner gate still decides), opens
with the digest, and keeps decisions as drafts: nothing moves a lane until the
owner texts ``YES <code>`` after the call.

Inbound works too: the owner calls in and says "review"; the tool selector
loads the same pack and the tool descriptions carry the repeat-back rule.
"""

from __future__ import annotations

from typing import Any

REVIEW_BRIEF_PREFIX = "review:"
REVIEW_SPOKEN_FLAG = "review"

REVIEW_OPENING_TAIL = "Where do you want to start, or should I go idea by idea?"
REVIEW_OPENING_EMPTY = (
    "Charles has nothing new in staging, so this will be short. "
    "Anything you want me to note for him?"
)

# Appended to Samuel's instructions only on the outbound review leg.
REVIEW_OVERLAY = (
    "This is the owner's review call about Charles's staging area. "
    "Open with the digest you were handed, then go idea by idea. "
    "Give your own opinion in one sentence when asked. "
    "When the owner wants an artifact (research, problem statement, competitive analysis, "
    "user feedback, heuristics, brief, personas, UX, PRD), call get_proposal_artifact and read "
    "the part they asked about, not the whole thing. "
    "When the owner decides, repeat it back once ('accept the slippage dashboard?') and only then "
    "call draft_decision. Nothing moves until they text YES after the call; say so once, not every time. "
    "Use review_note for anything they want remembered. "
    "When they say wrap up or done, call finish_review and tell them to watch for the text."
)


def is_review_call(meta: dict[str, Any] | None) -> bool:
    """True when outbound metadata marks the leg as the owner's review call."""
    if not meta:
        return False
    spoken = str(meta.get("spoken") or "").strip().lower()
    brief = str(meta.get("brief") or "").strip().lower()
    return spoken == REVIEW_SPOKEN_FLAG or brief.startswith(REVIEW_BRIEF_PREFIX)


def review_digest_from_brief(brief: str) -> str:
    text = str(brief or "").strip()
    if text.lower().startswith(REVIEW_BRIEF_PREFIX):
        text = text[len(REVIEW_BRIEF_PREFIX):].strip()
    return text


def review_opening(meta: dict[str, Any] | None) -> str:
    """What Samuel says when the owner picks up: the digest plus one question."""
    digest = review_digest_from_brief(str((meta or {}).get("brief") or ""))
    if not digest:
        return REVIEW_OPENING_EMPTY
    if not digest.endswith((".", "!", "?")):
        digest += "."
    return f"{digest} {REVIEW_OPENING_TAIL}"


def resolve_outbound_spoken(meta: dict[str, Any] | None) -> str:
    """The literal first line for an outbound leg; review and Sentinel calls build it from the brief."""
    if is_review_call(meta):
        return review_opening(meta)
    from .sentinel_call import is_sentinel_call, sentinel_opening

    if is_sentinel_call(meta):
        return sentinel_opening(meta)
    return str((meta or {}).get("spoken") or "").strip()
