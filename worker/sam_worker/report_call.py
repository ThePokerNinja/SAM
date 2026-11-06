"""Owner call about one short report (a Monday card change, an answered idea, an undo, Pythia's offer).

rm_api's ``CALL ME`` text and the report page's "Call me" button dial the owner with ``brief="report: …"``
and ``spoken="report"``. The leg gets no tools: Sam explains the report and never approves anything. The
owner decides by texting YES with the code, or on the page.
"""

from __future__ import annotations

from typing import Any

REPORT_BRIEF_PREFIX = "report:"
REPORT_SPOKEN_FLAG = "report"

_OVERLAY = (
    "This is a short call with the owner about one report. It is below. "
    "Open with its headline. Answer only from the report, in short plain sentences, one idea at a time. "
    "No jargon, no math terms; say good days, not percentages of days. "
    "You cannot approve, change, or place anything on this call. If they want to use it, tell them to text YES "
    "and the code, or tap Yes on the page in the text. If they ask something the report does not say, say so "
    "and offer to put the question to the team.\n\nReport:\n"
)


def is_report_call(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    spoken = str(meta.get("spoken") or "").strip().lower()
    brief = str(meta.get("brief") or "").strip().lower()
    return spoken == REPORT_SPOKEN_FLAG or brief.startswith(REPORT_BRIEF_PREFIX)


def _body(meta: dict[str, Any] | None) -> str:
    brief = str((meta or {}).get("brief") or "").strip()
    if brief.lower().startswith(REPORT_BRIEF_PREFIX):
        brief = brief[len(REPORT_BRIEF_PREFIX):].strip()
    return brief[:1200]


def report_overlay(meta: dict[str, Any] | None) -> str:
    return _OVERLAY + (_body(meta) or "(empty)")


def report_opening(meta: dict[str, Any] | None) -> str:
    """Sam's first line: the report's headline, then one open question."""
    lines = [ln.strip() for ln in _body(meta).splitlines() if ln.strip()]
    if not lines:
        return "Hi, it's Sam. I don't have the report in front of me. Check the link in your text."
    head = lines[0] if lines[0].endswith((".", "!", "?")) else lines[0] + "."
    return f"Hi, it's Sam about your report. {head} What would you like to know?"
