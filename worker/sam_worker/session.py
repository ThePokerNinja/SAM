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
        kind = route_session_kind(
            surface=self.surface,
            keyword=utterance,
            room_name="",
            current_kind=self.kind,
        )
        if kind == self.kind:
            return False
        self.kind = kind
        self.pack = pack_for_kind(kind)
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
    if room.startswith("demo-") or room.startswith("intake-"):
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
    )
