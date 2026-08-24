"""Per-turn tool subset for the voice path (Wave 8.2).

Studio tools stay off the default voice path. Router-handled intents never reach
the LLM; this selector only runs on unrouted turns.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def _normalize(utterance: str) -> str:
    text = utterance.lower().replace("&", " and ")
    text = text.replace("'", "").replace("’", "")
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
    "send_email",
    "place_call",
    "reach",
    "ask_hermes",
    "text_me",
    "get_health",
    "read_research",
    "send_manual",
    "get_studio_run",
    "whois_person",
    "draft_for_person",
    "get_campaign",
    "request_doctor",
    "run_command",
    "build_status",
    "capabilities",
    "moderate_room",
    "grant_room",
    "send_demo",
    "set_memory",
    "proposal_apply_summary",
    "proposal_set_field",
    "proposal_focus",
    "proposal_ask_gap",
    "proposal_answer_question",
    "proposal_revise",
    "proposal_send",
)

STUDIO_TOOLS: tuple[str, ...] = (
    "list_studio_runs",
    "studio_asset_status",
    "studio_campaign_report",
    "make_studio_deliverable",
    "record_studio_publish",
)

CALENDAR_PACK_TOOLS: frozenset[str] = frozenset(
    {
        "get_calendar_events",
        "propose_calendar_change",
        "commit_calendar_change",
    }
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


_PRONOUNS = ("her", "him", "them", "she", "he")
_TRADE_WORDS = ("scan", "picks", "watchlist", "ticker", "pulse", "regime", "nvda", "board")
_WHO_AFTER = re.compile(
    r"\b(?:call|dial|text|sms|message|remind|tell)\s+"
    r"(her|him|them|she|he|they|[a-z][a-z'`-]{1,30})\b"
)


def _is_outreach_utterance(text: str, raw: str) -> bool:
    """Person reach, not a trading 'call'. Mirrors rm_api.outreach.is_outreach_utterance."""
    if not text:
        return False
    if _has_any(text, ("don't", "dont", "do not", "cancel")) and _has_any(
        text, ("call", "text", "sms", "that")
    ):
        return True
    if _has_any(text, ("prayer", "remind ", "remind her", "remind him", "tell her", "tell him")):
        return True
    if "can you call" in text or "can you text" in text:
        return True
    if re.search(r"\b(call|text|dial|sms)\s+(her|him|them|she|he)\b", text):
        return True
    match = _WHO_AFTER.search(text)
    if not match:
        return False
    who = match.group(1)
    if who in {"me", "that", "the", "a", "an", "my", "this", "it"}:
        return False
    if who in _TRADE_WORDS or _has_any(text, _TRADE_WORDS):
        if who not in _PRONOUNS and len(who) <= 5:
            return False
    return True


_CONFIRM_FORCE = re.compile(r"\b(book it|do it|go ahead|please book|confirm)\b")
_CONFIRM_YES = re.compile(r"\b(yes|yep|yeah|yup)\b")
_YES_OR_NO = re.compile(r"\byes or no\b")


def is_calendar_confirm(utterance: str) -> bool:
    """True only for a real commit, not "yes or no?" or "yeah, book an appointment"."""
    text = _normalize(utterance)
    if not text or _YES_OR_NO.search(text):
        return False
    if _CONFIRM_FORCE.search(text):
        return True
    if calendar_action_for_utterance(utterance):
        return False
    return bool(_CONFIRM_YES.search(text))


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
        return ["run_command"]
    if is_calendar_confirm(utterance):
        return ["commit_calendar_change", "run_command"]
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
    if _has_any(text, ("email", "e mail", "send a note to")):
        selected.append("send_email")
    if _is_outreach_utterance(text, raw):
        selected.append("reach")
    elif _has_any(text, ("place a call", "place the call", "outbound")):
        selected.append("place_call")
    if _has_any(
        text,
        (
            "what should i learn",
            "what should you learn",
            "improvement idea",
            "ask for help",
            "second opinion",
            "skill idea",
        ),
    ):
        selected.append("ask_hermes")
    if _has_any(text, ("text me", "text that", "sms me", "send that to my phone")):
        selected.append("text_me")
    if _has_any(text, ("health", "status", "are you up")):
        selected.append("get_health")
    if _has_any(text, ("read idea", "read research")):
        selected.append("read_research")
    if _has_any(text, ("user manual", "samuel manual")):
        selected.append("send_manual")
    if "studio run" in text:
        selected.append("get_studio_run")
    if _has_any(text, ("whois", "who is")):
        selected.append("whois_person")
    if "draft" in text and _has_any(text, ("email", "person")):
        selected.append("draft_for_person")
    if "campaign" in text:
        selected.append("get_campaign")
    if _has_any(text, ("restart the api", "doctor", "deploy hook")):
        selected.append("request_doctor")
    if _has_any(text, ("what's being built", "whats being built", "build status", "next steps")):
        selected.append("build_status")
    if _has_any(text, ("what can you do", "what skills", "capabilities", "full catalog")):
        selected.append("capabilities")
    if "moderate" in text:
        selected.append("moderate_room")
    if _has_any(text, ("grant them", "grant a demo")):
        selected.append("grant_room")
    if _has_any(text, ("demo link", "send the demo")):
        selected.append("send_demo")
    if _has_any(text, ("memory on", "memory off", "forget me")):
        selected.append("set_memory")
    if _has_any(text, ("centaur idea", "queue this idea", "write a prd")):
        selected.append("centaur_idea")
    if _has_any(
        text,
        (
            "proposal",
            "sow",
            "estimate",
            "scope",
            "job title",
            "project name",
            "opening summary",
            "email this",
            "send this",
            "website",
            "branding",
        ),
    ) or len(text) >= 80:
        selected.extend(
            [
                "proposal_apply_summary",
                "proposal_set_field",
                "proposal_focus",
                "proposal_ask_gap",
                "proposal_answer_question",
                "proposal_revise",
                "proposal_send",
            ]
        )
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

    if "run_command" not in ordered:
        ordered.append("run_command")

    if len(ordered) > 1:
        return ordered
    if _has_any(text, _RAINMAKERISH):
        return [*_FALLBACK_VOICE, "run_command"]
    return ["run_command"]


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
