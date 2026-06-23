"""Tier-T owner gate for trigger tools (run_scan, queue_research).

Until Picovoice Eagle is enrolled, the portal is already gated by SAM_PORTAL_ACCESS_KEY
at token mint - anyone in the room passed that check. Participant JWT attributes
(role=owner) are the preferred signal but can arrive late or not surface on the agent
SDK; this module caches attribute updates and falls back to "connected human in a
portal session" only while voice verify is NOT armed.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

_log = logging.getLogger("sam.owner_gate")


def participant_has_owner_role(ctx: Any) -> bool:
    """True when a remote participant carries role=owner from the access token."""
    try:
        for p in ctx.room.remote_participants.values():
            attrs = getattr(p, "attributes", None) or {}
            if attrs.get("role") == "owner":
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


class OwnerGate:
    """Session-scoped owner check for Tier-T tools."""

    def __init__(self, ctx: Any, verifier: Any | None) -> None:
        self._ctx = ctx
        self._verifier = verifier
        self._attr_owner = False

    def note_participant(self, participant: Any) -> None:
        attrs = getattr(participant, "attributes", None) or {}
        if attrs.get("role") == "owner":
            self._attr_owner = True

    def on_attributes_changed(self, _changed: list[str], participant: Any) -> None:
        self.note_participant(participant)

    def on_participant_connected(self, participant: Any) -> None:
        self.note_participant(participant)

    def refresh(self) -> None:
        if participant_has_owner_role(self._ctx):
            self._attr_owner = True

    def is_owner(self) -> bool:
        if self._verifier is not None and self._verifier.is_owner():
            return True
        self.refresh()
        if self._attr_owner:
            return True
        if self._verifier is not None:
            # Voice verify armed but no match yet - do not use portal fallback.
            return False
        # Interim: portal access-key gated the join; Pico not enrolled yet.
        connected = bool(getattr(self._ctx.room, "remote_participants", None))
        if connected:
            _log.debug("owner gate: portal fallback (voice verify off, human connected)")
        return connected


def build_owner_gate(ctx: Any, verifier: Any | None) -> tuple[Callable[[], bool], OwnerGate]:
    gate = OwnerGate(ctx, verifier)
    return gate.is_owner, gate


def wire_owner_gate_listeners(room: Any, gate: OwnerGate) -> None:
    """Subscribe to LiveKit participant events so role=owner is cached when it arrives."""

    @room.on("participant_connected")
    def _on_connected(participant: Any) -> None:
        gate.on_participant_connected(participant)

    @room.on("participant_attributes_changed")
    def _on_attrs(changed: list[str], participant: Any) -> None:
        gate.on_attributes_changed(changed, participant)

    # Seed from anyone already in the room when the agent joins.
    try:
        for p in room.remote_participants.values():
            gate.on_participant_connected(p)
    except Exception:  # noqa: BLE001
        pass
