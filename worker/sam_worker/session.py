"""SAM-038: Session context + SessionKind router.

Trading is the degenerate default so today's single-user flow does not break.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SessionKind = Literal["trading", "moderator", "appointment", "skillbuilder", "intake"]
SurfaceName = Literal["portal", "phone", "sms"]
Role = Literal["host", "party", "observer"]


@dataclass
class Participant:
    id: str
    role: Role = "host"
    display_name: str | None = None
    speaker_id: str | None = None


@dataclass
class Session:
    id: str
    kind: SessionKind = "trading"
    surface: SurfaceName = "portal"
    pack: str = "trading"
    participants: tuple[Participant, ...] = ()
    memory_scope: str = "owner"
    recording: bool = False
    paused: bool = False
    room_name: str = ""

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def add_party(self, participant_id: str, display_name: str | None = None) -> Participant:
        existing = next((item for item in self.participants if item.id == participant_id), None)
        if existing is not None:
            return existing
        party = Participant(id=participant_id, role="party", display_name=display_name)
        self.participants = (*self.participants, party)
        return party

    def bind_host(self, participant_id: str, display_name: str | None = None) -> Participant:
        host = Participant(id=participant_id, role="host", display_name=display_name)
        parties = tuple(item for item in self.participants if item.role != "host")
        self.participants = (host, *parties)
        return host

    def activate_from_utterance(self, utterance: str) -> bool:
        """Activate an explicitly requested pack before the current reply."""
        if not allows_pack_switch(self.kind):
            return False
        kind = route_session_kind(
            surface=self.surface,
            keyword=utterance,
            room_name=self.room_name,
            current_kind=self.kind,
        )
        if kind == self.kind:
            return False
        self.kind = kind
        self.pack = pack_for_kind(kind)
        return True


BUILDER_OPENING = "I'm Samuel. What's the thing you want to make real?"
BUILDER_REASK = "Whenever you're ready — what's the job?"


def should_speak_builder_opening(room_name: str) -> bool:
    return (room_name or "").lower().startswith("builder-")


def greeting_instructions(kind: SessionKind) -> str:
    """Spoken open. Intake is the builder; the voice portal stays the general greet."""
    if kind == "intake":
        return (
            "This is the proposal builder — a short, collaborative scoping call, "
            "not a general chat. In one spoken breath: you are Samuel, then ask "
            "what they want to make real. Invite a messy sketch — a concept, a "
            "business need, an idea they have not named yet. Then stop and listen. "
            "Do not ask how their day is. Do not list skills, tools, or pricing."
        )
    return (
        "Greet the user warmly as Samuel in one short spoken sentence, then ask how "
        "you can help. Do not promise any capabilities, pricing, or actions in the greeting."
    )


def is_builder_room(room_name: str) -> bool:
    """True for proposal-builder LiveKit rooms, including granted demo walks."""
    room = (room_name or "").lower()
    return room.startswith(
        ("builder-", "demo-builder-", "demo-", "intake-", "samuel-dial-")
    )


def allows_pack_switch(kind: SessionKind) -> bool:
    """Builder / intake rooms stay on the proposal pack. They are not moderator rooms."""
    return kind != "intake"


def allows_skill_approval_sms(kind: SessionKind, room_name: str = "") -> bool:
    """YES/NO skill-approval texts are an owner consent rail, not part of scoping a job."""
    if kind == "intake" or is_builder_room(room_name):
        return False
    return True


def pack_for_kind(kind: SessionKind) -> str:
    return {
        "trading": "trading",
        "moderator": "moderator",
        "appointment": "appointment",
        "skillbuilder": "skillbuilder",
        "intake": "intake",
    }.get(kind, "trading")


def route_session_kind(
    *,
    surface: str,
    keyword: str = "",
    room_name: str = "",
    current_kind: SessionKind = "trading",
) -> SessionKind:
    blob = f"{keyword} {room_name} {surface}".lower()
    room = (room_name or "").lower()
    if room.startswith("staging-") or "staging-" in blob:
        return "skillbuilder"
    if room.startswith("samuel-dial-"):
        return "intake"
    if room.startswith("mod-"):
        return "moderator"
    if room.startswith("demo-") or room.startswith("intake-") or room.startswith("builder-"):
        return "intake"
    if re.search(r"\b(moderat(?:e|or|ion)?|help us disagree|settle a disagreement)\b", blob):
        return "moderator"
    if re.search(r"\b(appointment|book (?:an? )?(?:appointment|meeting)|scheduling mode)\b", blob):
        return "appointment"
    if re.search(r"\b(skillbuilder|skill builder|advisory mode)\b", blob):
        return "skillbuilder"
    if re.search(r"\b(trading mode|rainmaker mode|back to trading)\b", blob):
        return "trading"
    return current_kind


def build_session(
    *,
    session_id: str,
    surface: str,
    keyword: str = "",
    room_name: str = "",
    owner_id: str = "owner",
) -> Session:
    kind = route_session_kind(surface=surface, keyword=keyword, room_name=room_name)
    pack = pack_for_kind(kind)
    surf: SurfaceName = "phone" if surface == "phone" else "sms" if surface == "sms" else "portal"
    host = Participant(id=owner_id, role="host")
    return Session(
        id=session_id,
        kind=kind,
        surface=surf,
        pack=pack,
        participants=(host,),
        room_name=room_name or "",
    )
