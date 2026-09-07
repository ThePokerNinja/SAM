"""SAM-038: Session context + SessionKind router.

Trading is the degenerate default so today's single-user flow does not break.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
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


def is_owner_inbound_phone_call(room_name: str) -> bool:
    """Owner dials 855 — LiveKit room is call-<caller>_<id>, not outbound samuel-dial-."""
    return (room_name or "").lower().startswith("call-")


def should_speak_builder_opening(room_name: str, *, is_phone: bool = False) -> bool:
    """Builder rooms only. Owner 855 greets as Samuel; sales is a later pack."""
    del is_phone
    return (room_name or "").lower().startswith("builder-")


def should_use_phone_phase2_agentic() -> bool:
    """855 Phase 2: LLM picks scoping tools; protocol still locks send. Off until operator unhold."""
    return os.environ.get("SAM_PHASE2_AGENTIC", "").strip().lower() in {"1", "true", "yes"}


def should_use_phone_listen_first_intake(
    room_name: str,
    kind: SessionKind,
    *,
    is_phone: bool = False,
) -> bool:
    """Owner 855 scoping: Samuel talks via LLM; notebook sync stays silent."""
    if should_use_phone_phase2_agentic():
        return False
    return bool(is_phone and kind == "intake" and (room_name or "").lower().startswith("call-"))


def should_use_builder_intake_path(
    room_name: str,
    kind: SessionKind,
    *,
    is_phone: bool = False,
) -> bool:
    """Deterministic proposal-tool turns for builder portal rooms only."""
    if should_use_phone_listen_first_intake(room_name, kind, is_phone=is_phone):
        return False
    if should_speak_builder_opening(room_name):
        return True
    return False


def greeting_instructions(kind: SessionKind) -> str:
    """Spoken open. Intake is the builder; the voice portal stays the general greet."""
    if kind == "intake":
        return (
            "You are Samuel helping scope a job they already asked to talk about. "
            "In one spoken breath: stay Samuel, then ask what they want to make "
            "real. Invite a messy sketch. Then stop and listen. Do not introduce "
            "yourself as a proposal builder. Do not ask how their day is."
        )
    return (
        "Greet the user warmly as Samuel in one short spoken sentence, then ask how "
        "you can help. Do not promise any capabilities, pricing, or actions in the greeting."
    )


def is_builder_test_room(room_name: str) -> bool:
    """Owner start. rooms only. Granted demos and the voice portal keep their own rails."""
    room = (room_name or "").lower()
    return room.startswith("builder-") or room.startswith("demo-builder-")


def allows_pack_switch(kind: SessionKind) -> bool:
    """Builder / intake rooms stay on the proposal pack. They are not moderator rooms."""
    return kind != "intake"


def allows_skill_approval_sms(kind: SessionKind, room_name: str = "") -> bool:
    """Skip YES/NO skill-approval texts while testing start. Keep them everywhere else."""
    if is_builder_test_room(room_name):
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
    if re.search(
        r"\b(website|reservation|menu|branding|pitch deck|proposal|estimate|scope|"
        r"instagram|campaign|app|logo|animation|deck|izakaya|cafe|founder|project|"
        r"talk about|make real|working on|business need)\b",
        blob,
    ):
        if surface == "phone" or room.startswith("call-"):
            return "intake"
    if re.search(r"\b(want to|wanna)\b", blob) and re.search(
        r"\b(talk|build|make|create|scope|discuss)\b", blob
    ):
        if surface == "phone" or room.startswith("call-"):
            return "intake"
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
