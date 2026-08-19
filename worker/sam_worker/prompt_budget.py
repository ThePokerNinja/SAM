"""SAM-078: per-turn prompt token budget (system / tool-schema / history).

The spoken canon is short. The TPM killer on Groq's 8K owner-pilot limit is the full tool-schema
dump plus growing chat. This module estimates that split without a live LLM call.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .personas import SAMUEL
from .tools.rainmaker_registry import register_rainmaker_tools
from .tools.registry import ToolRegistry, ToolSpec

# Target for a typical unrouted turn after Wave 8.2 shrink.
TARGET_PROMPT_TOKENS = 800
GROQ_TPM_BUDGET = 8000

# Hard cap on user/assistant history tokens sent to the LLM (on top of turn-count trim).
DEFAULT_HISTORY_TOKEN_CAP = 250

# One-line tool reminder. Schemas already say when to call; do not duplicate a brochure.
VOICE_TOOLS_APPENDIX = (
    "For live Rainmaker facts, call a tool and speak only what it returns. "
    "Never invent numbers."
)

# Known parameters for OpenAI-style schema reconstruction (LiveKit infers these
# from the handler signature; we mirror them so the token count matches the wire).
_TOOL_PARAMS: dict[str, dict[str, Any]] = {
    "queue_research": {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
        "required": ["topic"],
    },
    "studio_asset_status": {
        "type": "object",
        "properties": {"asset_id": {"type": "string"}},
        "required": ["asset_id"],
    },
    "studio_campaign_report": {
        "type": "object",
        "properties": {"run_id": {"type": "string"}},
        "required": ["run_id"],
    },
    "make_studio_deliverable": {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["type"],
    },
    "record_studio_publish": {
        "type": "object",
        "properties": {
            "asset_id": {"type": "string"},
            "url": {"type": "string"},
        },
        "required": ["asset_id", "url"],
    },
    "get_calendar_events": {
        "type": "object",
        "properties": {"days": {"type": "integer"}},
        "required": [],
    },
    "propose_calendar_change": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "cancel"],
            },
            "summary": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "duration_minutes": {"type": "integer"},
            "event_id": {"type": "string"},
            "event_query": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "all_day": {"type": "boolean"},
            "timezone": {"type": "string"},
        },
        "required": ["action"],
    },
    "commit_calendar_change": {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": [],
    },
}

_EMPTY_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}


def estimate_tokens(text: str) -> int:
    """Cheap cl100k-ish estimate: ~4 characters per token. Empty is zero."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def samuel_instructions(*, extra: str = "") -> str:
    """Canon + short tool reminder (+ optional bench/greeting extra)."""
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    calendar_hint = (
        f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}; "
        f"the time is {now.strftime('%I:%M %p').lstrip('0')} Pacific. "
        "For calendar changes, use ISO-8601 Pacific times, propose first, read it back, "
        "and wait for a later yes before committing. A create needs summary, start, and "
        "either end or duration_minutes. Never speak bracketed event IDs."
    )
    parts = [SAMUEL.system_hint.strip(), VOICE_TOOLS_APPENDIX, calendar_hint]
    extra = (extra or "").strip()
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def tool_openai_schema(spec: ToolSpec) -> dict[str, Any]:
    """Reconstruct the function-tool payload the LLM actually sees."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": _TOOL_PARAMS.get(spec.name, _EMPTY_PARAMS),
        },
    }


def tool_schema_text(spec: ToolSpec) -> str:
    return json.dumps(tool_openai_schema(spec), separators=(",", ":"), sort_keys=True)


def history_text(messages: Iterable[str]) -> str:
    return "\n".join(m for m in messages if m)


@dataclass
class PromptBudget:
    system_tokens: int
    tool_schema_tokens: int
    history_tokens: int
    total_tokens: int
    tool_count: int
    tool_names: list[str] = field(default_factory=list)
    system_chars: int = 0
    tool_schema_chars: int = 0
    history_chars: int = 0
    dominant: str = ""
    turns_per_minute_at_tpm_budget: float = 0.0
    under_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def breakdown(
    *,
    system: str,
    specs: Iterable[ToolSpec],
    history: Iterable[str] = (),
) -> PromptBudget:
    spec_list = list(specs)
    system_text = system or ""
    tools_text = "".join(tool_schema_text(spec) for spec in spec_list)
    hist_text = history_text(history)
    system_tokens = estimate_tokens(system_text)
    tool_tokens = estimate_tokens(tools_text)
    hist_tokens = estimate_tokens(hist_text)
    total = system_tokens + tool_tokens + hist_tokens
    slices = {
        "system": system_tokens,
        "tool_schema": tool_tokens,
        "history": hist_tokens,
    }
    dominant = max(slices, key=slices.get) if total else "system"
    tpm = (GROQ_TPM_BUDGET / total) if total else 0.0
    return PromptBudget(
        system_tokens=system_tokens,
        tool_schema_tokens=tool_tokens,
        history_tokens=hist_tokens,
        total_tokens=total,
        tool_count=len(spec_list),
        tool_names=[spec.name for spec in spec_list],
        system_chars=len(system_text),
        tool_schema_chars=len(tools_text),
        history_chars=len(hist_text),
        dominant=dominant,
        turns_per_minute_at_tpm_budget=round(tpm, 2),
        under_target=total <= TARGET_PROMPT_TOKENS,
    )


def all_rainmaker_specs() -> list[ToolSpec]:
    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    return registry.specs()


def specs_named(names: Iterable[str], *, registry: ToolRegistry | None = None) -> list[ToolSpec]:
    if registry is None:
        registry = ToolRegistry()
        register_rainmaker_tools(registry)
    out: list[ToolSpec] = []
    for name in names:
        spec = registry.get(name)
        if spec is None:
            raise KeyError(f"unknown tool: {name}")
        out.append(spec)
    return out
