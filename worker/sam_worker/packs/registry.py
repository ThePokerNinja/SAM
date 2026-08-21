"""SAM-039: skill-pack registry + manifest loader with pre-warm."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackManifest:
    id: str
    persona_overlay: str
    tools: tuple[str, ...]
    workflow: tuple[str, ...]
    memory_schema: str = "owner"
    safety_rules: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    prewarm: bool = True


TRADING = PackManifest(
    id="trading",
    persona_overlay="You are Samuel, the Rainmaker trading agent. Ground every market claim in a tool.",
    # Empty tools = degenerate default: keep the full Rainmaker set so today's flow does not shrink.
    tools=(),
    workflow=("ground", "answer"),
    artifacts=("summary",),
)

MODERATOR = PackManifest(
    id="moderator",
    persona_overlay=(
        "You are Samuel hosting two people who disagree. Stay neutral. "
        "Do not take a side, assign blame, or diagnose. Map agree / unlikely / "
        "can't / won't / absolutely-won't. Either party may pause or end."
    ),
    tools=("capture_note", "list_captures"),
    workflow=("intake", "moderate", "close"),
    safety_rules=("neutrality", "no_recording_default", "graceful_exit"),
    artifacts=("understanding_map", "next_steps"),
)

APPOINTMENT = PackManifest(
    id="appointment",
    persona_overlay="You are Samuel booking on the owner's calendar. Read back times exactly. Never commit until they confirm.",
    tools=("get_calendar_events", "propose_calendar_change", "commit_calendar_change"),
    workflow=("find", "propose", "confirm"),
    artifacts=("action_item",),
)

SKILLBUILDER = PackManifest(
    id="skillbuilder",
    persona_overlay=(
        "You are Samuel coaching the owner through a measurable skill. "
        "Ask one diagnostic question at a time, keep advice reversible, and record "
        "evidence before changing a score or state."
    ),
    tools=("capture_note", "list_captures"),
    workflow=("diagnose", "practice", "score", "recommend"),
    memory_schema="skill_snapshot",
    safety_rules=("advisory_only", "owner_correction"),
    artifacts=("summary", "next_steps"),
)


class PackRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, PackManifest] = {}
        self._warm: set[str] = set()
        self._active_id = "trading"
        for pack in (TRADING, MODERATOR, APPOINTMENT, SKILLBUILDER):
            self.register(pack)

    def register(self, pack: PackManifest) -> None:
        self._packs[pack.id] = pack
        if pack.prewarm:
            self._warm.add(pack.id)

    def get(self, pack_id: str) -> PackManifest:
        return self._packs.get(pack_id) or TRADING

    def unload(self, pack_id: str) -> None:
        self._warm.discard(pack_id)
        if self._active_id == pack_id:
            self._active_id = "trading"

    def activate(self, pack_id: str) -> PackManifest:
        pack = self.get(pack_id)
        self._warm.add(pack.id)
        self._active_id = pack.id
        return pack

    @property
    def active_id(self) -> str:
        return self._active_id

    def is_warm(self, pack_id: str) -> bool:
        return pack_id in self._warm

    def ids(self) -> tuple[str, ...]:
        return tuple(self._packs)

    def tools_for(self, pack_id: str, available: list[str]) -> list[str] | None:
        """None means all tools (trading's degenerate default)."""
        pack = self.get(pack_id)
        if pack.id == "trading" or not pack.tools:
            return None
        allowed = set(pack.tools)
        return [name for name in available if name in allowed]
