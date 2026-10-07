"""SAM-038: Session context + SessionKind router.

Trading is the degenerate default so today's single-user flow does not break.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import re
from typing import Literal
from zoneinfo import ZoneInfo

SessionKind = Literal["trading", "moderator", "appointment", "skillbuilder", "intake", "brainstorm"]
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
        if not allows_pack_switch(self.kind, self.room_name):
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


def greeting_instructions(
    kind: SessionKind,
    *,
    now: datetime | None = None,
    prior_hook: str = "",
    last_opener: str = "",
    standing: str = "",
) -> str:
    """Spoken open. Intake is the builder; an owner call uses the clock and last thread."""
    if kind == "intake":
        return (
            "You are Samuel helping scope a job they already asked to talk about. "
            "In one spoken breath: stay Samuel, then ask what they want to make "
            "real. Invite a messy sketch. Then stop and listen. Do not introduce "
            "yourself as a proposal builder. Do not ask how their day is."
        )
    moment = now or datetime.now(ZoneInfo("America/Los_Angeles"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    else:
        moment = moment.astimezone(ZoneInfo("America/Los_Angeles"))
    clock = (
        f"{moment.strftime('%A, %B')} {moment.day}, "
        f"{moment.strftime('%I:%M %p').lstrip('0')}"
    )
    situation = ""
    if moment.strftime("%A") in {"Tuesday", "Thursday"} and 6 <= moment.hour < 10:
        situation = (
            " Sounds like you might be heading toward the office. "
            "Correct that if it's wrong."
        )
    hook = f" Mention this from last time: {prior_hook.strip()}." if prior_hook.strip() else ""
    repeat = (
        f" Do not repeat this previous opener: {last_opener.strip()}."
        if last_opener.strip()
        else ""
    )
    remembered = (
        f" Standing instructions you already accepted: {standing.strip()}."
        if standing.strip()
        else ""
    )
    return (
        "Open as Samuel in one spoken sentence, then stop and listen. "
        f"Right now it is {clock} Pacific.{situation}{hook}{repeat}{remembered} "
        "Do not ask what they need. Do not list capabilities, pricing, or actions. "
        "If you already have an approved proposal with them, you may mention it."
    )


def opener_facts(*, now: datetime, prior_hook: str = "") -> str:
    """Facts used in the opener, stored so the next call does not reuse the sentence."""
    moment = now if now.tzinfo else now.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    clock = (
        f"{moment.strftime('%A, %B')} {moment.day}, "
        f"{moment.strftime('%I:%M %p').lstrip('0')}"
    )
    parts = [clock]
    if moment.strftime("%A") in {"Tuesday", "Thursday"} and 6 <= moment.hour < 10:
        parts.append("heading toward the office")
    if prior_hook.strip():
        parts.append(prior_hook.strip()[:180])
    return " | ".join(parts)


def with_pack_honesty(base: str, overlay: str, pack_id: str) -> str:
    """Intake must not keep the trading brochure beside a pack that forbids those tools."""
    if pack_id == "intake":
        prefix = (
            "This turn's tools are the proposal notebook. Keep drafting, editing, and "
            "saving that proposal. Do not claim scans, pulse, trades, or a calendar "
            "reminder unless that tool is also attached. If you already said you could "
            "and the tool is missing, say so in one clause and continue the proposal.\n\n"
        )
    else:
        prefix = (
            "Claim a capability only when its tool is attached to this turn. "
            "If you already said you could and the tool is missing, say so in one clause "
            "and do the closest real action. Do not recite a skill list. "
            "Do not send them to the Morning app instead of calling a tool you have. "
            "When a proposal is in progress, keep it: draft, take their edits, and on "
            "approval save it and say they can review it at the start.michaelstewman.com "
            "link the tool returned. When they ask for a reminder, call "
            "propose_calendar_change and put the approved notes in the description.\n\n"
        )
    body = f"{base}\n\n{overlay}" if overlay.strip() else base
    return prefix + body


def is_builder_test_room(room_name: str) -> bool:
    """Owner start. rooms only. Granted demos and the voice portal keep their own rails."""
    room = (room_name or "").lower()
    return room.startswith("builder-") or room.startswith("demo-builder-")


def allows_pack_switch(kind: SessionKind, room_name: str = "") -> bool:
    """Builder rooms stay on the proposal pack. An owner 855 call can leave it."""
    if kind != "intake":
        return True
    room = (room_name or "").lower()
    if room.startswith(("builder-", "demo-", "intake-", "samuel-dial-")):
        return False
    return room.startswith("call-")


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
        "brainstorm": "brainstorm",
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
    if (surface == "phone" or room.startswith("call-")) and re.search(
        r"\b(continue|resume|pick (?:this|it) back up|where were we|same job)\b",
        blob,
    ):
        return "intake"
    if room.startswith("mod-"):
        return "moderator"
    if room.startswith("brainstorm-"):
        return "brainstorm"
    if room.startswith("demo-") or room.startswith("intake-") or room.startswith("builder-"):
        return "intake"
    # Portal and brainstorm rooms. Owner 855 stays on the full tool set so a
    # proposal and a calendar reminder can both run.
    if re.search(r"\b(brainstorm(?:ing)?(?: mode| session)?|think out loud|riff with me|let me talk (?:this|it) through)\b", blob):
        if not room.startswith("call-"):
            return "brainstorm"
    if re.search(r"\b(moderat(?:e|or|ion)?|help us disagree|settle a disagreement)\b", blob):
        return "moderator"
    if re.search(r"\b(appointment|book (?:an? )?(?:appointment|meeting)|scheduling mode)\b", blob):
        return "appointment"
    if re.search(r"\b(skillbuilder|skill builder|advisory mode)\b", blob):
        return "skillbuilder"
    if re.search(r"\b(trading mode|rainmaker mode|back to trading)\b", blob):
        return "trading"
    if room.startswith("call-") and re.search(
        r"\b(this isn'?t a proposal|not a proposal|stop scoping|"
        r"don'?t (?:want|wanna)(?: to)? talk about rainmaker|"
        r"dont (?:want|wanna)(?: to)? talk about rainmaker)\b",
        blob,
    ):
        return "trading"
    if room.startswith("call-"):
        # "working on" / "talk about" must not lock the commute into proposal-only tools.
        # The proposal itself stays available through the router once they start one.
        return current_kind
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
