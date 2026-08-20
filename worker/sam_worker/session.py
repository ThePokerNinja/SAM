"""SAM-038: Session context + SessionKind router.

Trading is the degenerate default so today's single-user flow does not break.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionKind = Literal["trading", "moderator", "appointment", "skillbuilder"]
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
        party = Participant(id=participant_id, role="party", display_name=display_name)
        self.participants = (*self.participants, party)
        return party


def route_session_kind(
    *,
    surface: str,
    keyword: str = "",
    room_name: str = "",
) -> SessionKind:
    blob = f"{keyword} {room_name} {surface}".lower()
    if "moderat" in blob or "disagree" in blob:
        return "moderator"
    if "appoint" in blob or "book" in blob or "calendar" in blob:
        return "appointment"
    return "trading"


def build_session(
    *,
    session_id: str,
    surface: str,
    keyword: str = "",
    room_name: str = "",
    owner_id: str = "owner",
) -> Session:
    kind = route_session_kind(surface=surface, keyword=keyword, room_name=room_name)
    pack = {"trading": "trading", "moderator": "moderator", "appointment": "appointment"}.get(
        kind, "trading"
    )
    surf: SurfaceName = "phone" if surface == "phone" else "sms" if surface == "sms" else "portal"
    host = Participant(id=owner_id, role="host")
    return Session(
        id=session_id,
        kind=kind,
        surface=surf,
        pack=pack,
        participants=(host,),
    )
