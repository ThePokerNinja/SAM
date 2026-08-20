"""Per-turn tool subset for the voice path (Wave 8.2).

Studio tools stay off the default voice path. Router-handled intents never reach
the LLM; this selector only runs on unrouted turns.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def _normalize(utterance: str) -> str:
    text = utterance.lower().replace("&", " and ")
    text = re.sub(r"['’]s\b", "s", text)
    return " ".join(_NON_ALNUM.sub(" ", text).split())


VOICE_TOOLS: tuple[str, ...] = (
    "get_scans",
    "get_pulse",
    "get_trades",
    "get_research",
    "run_scan",
    "queue_research",
    "capture_note",
    "list_captures",
    "get_brief",
    "send_brief",
    "send_hero",
)

STUDIO_TOOLS: tuple[str, ...] = (
    "list_studio_runs",
    "studio_asset_status",
    "studio_campaign_report",
    "make_studio_deliverable",
    "record_studio_publish",
)

# Tiny fallback when the utterance is Rainmaker-ish but no specific tool matched.
_FALLBACK_VOICE: tuple[str, ...] = ("get_pulse", "get_scans")

_TICKER = re.compile(r"\b[A-Z]{1,5}\b")

_RAINMAKERISH = (
    "rainmaker",
    "scan",
    "pick",
    "watchlist",
    "pulse",
    "regime",
    "tape",
    "market",
    "trade",
    "position",
    "pnl",
    "p and l",
    "research",
    "brief",
    "hero",
    "ticker",
    "board",
)


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def calendar_action_for_utterance(utterance: str) -> str | None:
    """Map explicit scheduling verbs to the proposal action they permit."""
    text = _normalize(utterance)
    if _has_any(text, ("cancel", "delete", "remove", "clear")):
        return "cancel"
    if _has_any(text, ("move", "reschedule", "change", "update", "shift", "edit")):
        return "update"
    if _has_any(text, ("book", "create", "add", "put", "hold")) or re.search(
        r"\bschedule (?:a |an |the |my )?(?:meeting|appointment|event|call|coffee|lunch)\b",
        text,
    ):
        return "create"
    if (
        _has_any(text, ("schedule", "calendar", "appointments", "meetings"))
        and _has_any(
            text,
            (
                "what is on",
                "whats on",
                "show",
                "read",
                "check",
                "do i have",
                "my schedule",
                "my calendar",
                "upcoming",
            ),
        )
    ):
        return None
    return None


def select_tools_for_utterance(utterance: str) -> list[str]:
    """Return the tool names the LLM should see for this utterance.

    Empty means no tools — correct for pricing, stories, and general chat.
    """
    text = _normalize(utterance)
    raw = utterance or ""
    if _has_any(text, ("cost", "price", "pricing", "fee", "fees", "how much")):
        return []
    if _has_any(text, ("story", "joke", "trivia", "poem")):
        return []
    if _has_any(text, ("yes", "confirm", "do it", "book it", "go ahead")):
        return ["commit_calendar_change"]
    selected: list[str] = []

    if _has_any(text, ("studio", "campaign", "deliverable", "asset id", "render")):
        selected.extend(STUDIO_TOOLS)

    if _has_any(text, ("scan", "picks", "watchlist", "board")):
        selected.append("get_scans")
        if _has_any(text, ("run", "refresh", "re run", "trigger", "start")):
            selected.append("run_scan")
    if _has_any(text, ("pulse", "regime", "mood", "tape", "bias")) or (
        "market" in text and _has_any(text, ("how", "what", "look"))
    ):
        selected.append("get_pulse")
    if _has_any(text, ("trade", "position", "pnl", "p and l", "balance", "holding")):
        selected.append("get_trades")
    if "research" in text:
        selected.append("get_research")
        if _has_any(text, ("queue", "look up", "lookup", "research this", "research that")):
            selected.append("queue_research")
    if _has_any(text, ("note", "notes", "task", "tasks", "remember this", "capture", "sync")):
        selected.append("list_captures")
        if _has_any(text, ("save", "add", "remember", "note that", "task", "capture")):
            selected.append("capture_note")
    if "brief" in text or "whats on today" in text or "what is on today" in text:
        selected.append("get_brief")
        if _has_any(text, ("text", "send", "sms")):
            selected.append("send_brief")
    if _has_any(text, ("hero", "character card", "stats card")):
        selected.append("send_hero")
    calendar_action = calendar_action_for_utterance(utterance)
    if calendar_action:
        selected.append("propose_calendar_change")
    elif _has_any(
        text,
        (
            "calendar",
            "schedule",
            "scheduling",
            "meeting",
            "appointment",
            "event",
            "coffee",
            "lunch",
        ),
    ):
        selected.append("get_calendar_events")
    if (
        _has_any(text, ("queue research", "research"))
        and _TICKER.search(raw)
        and "queue_research" not in selected
    ):
        selected.append("queue_research")

    # Dedup, preserve order.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in selected:
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    if ordered:
        return ordered

    if _has_any(text, _RAINMAKERISH):
        return list(_FALLBACK_VOICE)
    return []


def filter_tools(tools: list[object], names: list[str]) -> list[object]:
    """Keep LiveKit function tools whose name is in ``names`` (order of names)."""
    by_name: dict[str, object] = {}
    for tool in tools:
        name = tool_callable_name(tool)
        if name:
            by_name[name] = tool
    return [by_name[name] for name in names if name in by_name]


def tool_callable_name(tool: object) -> str:
    info = getattr(tool, "info", None) or getattr(tool, "_info", None)
    if info is not None:
        name = getattr(info, "name", None)
        if name:
            return str(name)
    return str(getattr(tool, "__name__", "") or "")
