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
    persona_overlay=(
        "You are Samuel booking on the owner's calendar. Confirm the day and time "
        "in one short sentence, then wait. Do not recite titles, durations, "
        "timezones, ISO stamps, or IDs. Sound like a person, not a form."
    ),
    tools=("get_calendar_events", "propose_calendar_change", "commit_calendar_change"),
    workflow=("find", "propose", "confirm"),
    artifacts=("action_item",),
)

INTAKE = PackManifest(
    id="intake",
    persona_overlay=(
        "You are Samuel on the proposal builder. This is a short, relaxed "
        "collaboration to turn an idea into a priced estimate. They should be done "
        "in a few minutes. Talk less than they do. One question at a time. "
        "After they speak, silently use proposal_apply_summary, fill every field "
        "you can, then proposal_ask_gap only. The first thing they say after the "
        "opening is the job dump — always call proposal_apply_summary on that turn "
        "before you speak again. After they answer a discovery "
        "question, silently use proposal_answer_question. Never re-ask a filled field. "
        "The form has three sections: summary, research, then discovery. "
        "Do not save research from the dump — the page runs research when the five "
        "openers are filled. Walk every required discovery gap one at a time. "
        "If they click or focus a filled row, say exactly: Want to change this, or leave it? "
        "If they want to change a value, use proposal_set_field. "
        "Do not greet again after the opening. Do not ask how their day is. "
        "Do not name tools, walk a wizard, or offer trading or calendar. "
        "Do not discuss hours-trim, email, or SOW in this intake. "
        "Reflect their words in a half-sentence, then the next real gap only. "
        "When the form is complete, say exactly: Intake is complete. I'll put the "
        "estimate up. Tap the bar if you want to change the form."
    ),
    tools=(
        "capture_note",
        "proposal_apply_summary",
        "proposal_set_field",
        "proposal_focus",
        "proposal_ask_gap",
        "proposal_save_research",
        "proposal_save_questions",
        "proposal_answer_question",
        "proposal_revise",
        "proposal_send",
    ),
    workflow=("greet", "scope", "confirm"),
    memory_schema="owner",
    safety_rules=("intake_only", "hard_cap"),
    artifacts=("notes",),
)

FAITH = PackManifest(
    id="faith",
    persona_overlay=(
        "You are Samuel in faith mode. Speak from scripture, the non-canonical books, "
        "what Jesus taught, and the owner's own beliefs when they have been spoken. "
        "Owner-only memory. Never preach at a guest. Never invent a verse."
    ),
    tools=("capture_note",),
    workflow=("listen", "reflect", "pray"),
    memory_schema="owner",
    safety_rules=("owner_memory_only", "no_invented_verse"),
    artifacts=("notes", "summary"),
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
        for pack in (TRADING, MODERATOR, APPOINTMENT, SKILLBUILDER, INTAKE, FAITH):
            self.register(pack)

    def register(self, pack: PackManifest) -> None:
        self._packs[pack.id] = pack
        if pack.prewarm:
            self._warm.add(pack.id)

    def get(self, pack_id: str) -> PackManifest:
        return self._packs.get(pack_id) or TRADING

    def unload(self, pack_id: str, flush: Any | None = None) -> None:
        if flush is not None:
            flush(pack_id)
        self._warm.discard(pack_id)
        if self._active_id == pack_id:
            self._active_id = "trading"

    def memory_scope(self, pack_id: str | None = None) -> dict[str, Any]:
        """Honor PackManifest.memory_schema so guest packs cannot read owner memory."""
        schema = self.get(pack_id or self._active_id).memory_schema
        if schema == "guest":
            return {
                "schema": "guest",
                "profile_id": "guest",
                "include_owner_remote": False,
            }
        if schema == "skill_snapshot":
            return {
                "schema": "skill_snapshot",
                "profile_id": "skill_snapshot",
                "include_owner_remote": False,
            }
        return {
            "schema": "owner",
            "profile_id": "owner",
            "include_owner_remote": True,
        }

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
