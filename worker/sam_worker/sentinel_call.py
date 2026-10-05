"""Owner call for a Sentinel warning.

rm_api's SMS keyword ``TALK`` dials the owner with ``brief="sentinel: …"`` and
``spoken="sentinel"``. The brief carries a one-time code. ``charles_decide``
sends that code back so pause and resume hit the same functions as the texts.
The owner never hears the code.
"""

from __future__ import annotations

from typing import Any

SENTINEL_BRIEF_PREFIX = "sentinel:"
SENTINEL_SPOKEN_FLAG = "sentinel"

SENTINEL_OVERLAY = (
    "This is a Sentinel call about Charles. Open with the situation you were handed. "
    "Ask that one question. "
    "If they say yes, call charles_decide with the action named on the action line of your brief. "
    "If they say no, call charles_decide with leave. "
    "Never say pause, resume, or resume anyway. "
    "Say the one sentence the tool returns. "
    "If the tool tells you to have them text YES, read that and do not say you already did it. "
    "Never mention a code."
)


def is_sentinel_call(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    spoken = str(meta.get("spoken") or "").strip().lower()
    brief = str(meta.get("brief") or "").strip().lower()
    return spoken == SENTINEL_SPOKEN_FLAG or brief.startswith(SENTINEL_BRIEF_PREFIX)


def code_from_brief(brief: str) -> str:
    for line in str(brief or "").splitlines():
        text = line.strip()
        if text.lower().startswith("code="):
            return text.split("=", 1)[1].strip().upper()
    return ""


def sentinel_opening(meta: dict[str, Any] | None) -> str:
    """What Samuel says when the owner picks up. The code line stays out."""
    brief = str((meta or {}).get("brief") or "").strip()
    if brief.lower().startswith(SENTINEL_BRIEF_PREFIX):
        brief = brief[len(SENTINEL_BRIEF_PREFIX):].strip()
    lines = [
        ln.strip()
        for ln in brief.splitlines()
        if ln.strip() and not ln.strip().lower().startswith(("code=", "action="))
    ]
    # The dial brief adds tool instructions after the situation. Speak only the situation.
    situation = lines[0] if lines else ""
    if not situation:
        return "This is Sentinel. Charles is still running. You can tell me to stop him or leave him running."
    if not situation.endswith((".", "!", "?")):
        situation += "."
    return situation
