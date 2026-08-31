"""Phase 5.0: owner continuity — history caps, rolling summaries, thread assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .demo_cap import is_capped_room
from .intake import BriefItem, SessionBrief, assemble_brief
from .session import is_builder_test_room as is_builder_room

DEFAULT_OWNER_HISTORY_TOKEN_CAP = 6000
DEFAULT_OWNER_MEMORY_TOKEN_CAP = 1200
DEFAULT_GUEST_HISTORY_TOKEN_CAP = 250

_OPEN_LOOP_MARKERS = (
    "still need",
    "open loop",
    "todo",
    "follow up",
    "next step",
    "we will",
    "i will",
    "let's ",
)


def effective_history_token_cap(
    settings: Any,
    *,
    is_owner: bool,
    room_name: str,
) -> int:
    """Guest demo rooms keep the tight cap; owner/builder sessions get the long window."""
    if is_capped_room(room_name):
        return max(1, int(getattr(settings, "history_token_cap", DEFAULT_GUEST_HISTORY_TOKEN_CAP)))
    if is_owner:
        return max(
            1,
            int(getattr(settings, "owner_history_token_cap", DEFAULT_OWNER_HISTORY_TOKEN_CAP)),
        )
    return max(1, int(getattr(settings, "history_token_cap", DEFAULT_GUEST_HISTORY_TOKEN_CAP)))


def owner_memory_token_cap(settings: Any) -> int:
    return max(
        256,
        int(getattr(settings, "owner_memory_token_cap", DEFAULT_OWNER_MEMORY_TOKEN_CAP)),
    )


def build_rolling_summary(
    turns: list[tuple[str, str]],
    *,
    max_chars: int = 2400,
    tail_turns: int = 8,
) -> str:
    """Compress the live thread so eviction does not erase the job dump."""
    if not turns:
        return ""
    parts: list[str] = []
    first_user = next((text for role, text in turns if role == "user" and text.strip()), "")
    if first_user:
        parts.append(f"Opening: {first_user[:900]}")
    recent = turns[-max(1, tail_turns) :]
    if len(turns) > tail_turns:
        parts.append(
            "Recent: "
            + " | ".join(f"{role}: {text[:240]}" for role, text in recent if text.strip())
        )
    else:
        parts.append(
            "Thread: "
            + " | ".join(f"{role}: {text[:240]}" for role, text in turns if text.strip())
        )
    joined = " ".join(parts).strip()
    return joined[:max_chars]


def extract_open_loops(turns: list[tuple[str, str]], *, limit: int = 6) -> tuple[str, ...]:
    loops: list[str] = []
    for role, text in turns:
        if role != "user":
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in _OPEN_LOOP_MARKERS):
            loops.append(text[:320])
    return tuple(loops[-limit:])


def build_thread_summary_text(
    turns: list[tuple[str, str]],
    *,
    engagement_id: str = "",
    room_name: str = "",
) -> str:
    """Durable cross-session summary written at hangup."""
    if not turns:
        return ""
    rolling = build_rolling_summary(turns, max_chars=1800, tail_turns=10)
    loops = extract_open_loops(turns)
    header = []
    if engagement_id:
        header.append(f"engagement={engagement_id}")
    if room_name:
        header.append(f"room={room_name}")
    lines = []
    if header:
        lines.append(" ".join(header))
    lines.append(rolling)
    if loops:
        lines.append("Open loops: " + " | ".join(loops))
    return "\n".join(line for line in lines if line.strip())[:4000]


def engagement_fields_for_context(engagement: dict[str, Any] | None) -> str:
    if not engagement:
        return ""
    answers = engagement.get("answers") or {}
    if not isinstance(answers, dict):
        answers = {}
    fields = [
        ("client", engagement.get("client_name") or answers.get("clientName")),
        ("project", engagement.get("project_name") or answers.get("projectName")),
        ("summary", answers.get("summary") or answers.get("openingSummary")),
        ("stage", engagement.get("stage")),
    ]
    rendered = []
    for key, value in fields:
        text = str(value or "").strip()
        if text:
            rendered.append(f"{key}={text[:400]}")
    return "; ".join(rendered)


def brief_from_thread_summary(
    thread: dict[str, Any] | None,
    *,
    artifact_brief: SessionBrief | None = None,
    builder_context: str = "",
) -> SessionBrief:
    items: list[BriefItem] = []
    if isinstance(thread, dict) and str(thread.get("summary") or "").strip():
        updated = thread.get("updatedAt") or thread.get("updated_at")
        provenance = "thread_summary"
        if updated:
            provenance = f"thread_summary:{updated}"
        items.append(
            BriefItem(
                text=str(thread["summary"]).strip()[:2000],
                provenance=provenance,
                confidence=1.0,
                consent=True,
            )
        )
        loops = thread.get("openLoops") or thread.get("open_loops") or []
        if isinstance(loops, list) and loops:
            items.append(
                BriefItem(
                    text="Open loops: " + " | ".join(str(item)[:200] for item in loops[:6]),
                    provenance="thread_summary:open_loops",
                    confidence=0.95,
                    consent=True,
                )
            )
    if builder_context.strip():
        items.append(
            BriefItem(
                text=f"Current proposal builder state: {builder_context[:1200]}",
                provenance="builder_engagement",
                confidence=1.0,
                consent=True,
            )
        )
    if artifact_brief is not None and artifact_brief.items:
        items.extend(artifact_brief.items)
    return assemble_brief(tuple(items))


def is_builder_room_name(room_name: str) -> bool:
    return is_builder_room(room_name)


@dataclass(frozen=True)
class ContinuityState:
    rolling_summary: str = ""
    engagement_id: str = ""
    room_name: str = ""

    def update_turns(self, turns: list[tuple[str, str]]) -> ContinuityState:
        return ContinuityState(
            rolling_summary=build_rolling_summary(turns),
            engagement_id=self.engagement_id,
            room_name=self.room_name,
        )
