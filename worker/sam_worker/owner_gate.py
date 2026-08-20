"""Tier-T owner gate for trigger tools (run_scan, queue_research).

Owner is proven by one of:

- a live voiceprint match when Eagle is armed,
- JWT attribute ``role=owner`` minted after Google / verified portal auth, or
- a SIP caller whose ``sip.phoneNumber`` is in ``SAM_SIP_OWNER_NUMBERS``.

The gate fails closed. A connected human without one of those proofs is not
the owner, so retiring ``SAM_PORTAL_ACCESS_KEY`` cannot hand owner-tier tools
to anyone who merely reaches a room.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Callable

_log = logging.getLogger("sam.owner_gate")


def _digits(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def sip_caller_is_authorized(
    participants: Iterable[Any],
    owner_numbers: Iterable[str],
) -> bool:
    """Defense-in-depth caller gate behind LiveKit trunk ``allowed_numbers``."""
    allowed = {_digits(number) for number in owner_numbers}
    allowed.discard("")
    callers = {
        _digits(
            (getattr(participant, "attributes", None) or {}).get("sip.phoneNumber", "")
        )
        for participant in participants
    }
    callers.discard("")
    return bool(callers) and not callers.isdisjoint(allowed)


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

    def __init__(
        self,
        ctx: Any,
        verifier: Any | None,
        sip_owner_numbers: Iterable[str] = (),
    ) -> None:
        self._ctx = ctx
        self._verifier = verifier
        self._sip_owner_numbers = tuple(sip_owner_numbers or ())
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
            # Voice verify armed but no match yet - do not use a weaker fallback.
            return False
        try:
            participants = list(self._ctx.room.remote_participants.values())
        except Exception:  # noqa: BLE001
            return False
        if self._sip_owner_numbers and sip_caller_is_authorized(
            participants, self._sip_owner_numbers
        ):
            return True
        return False


def build_owner_gate(
    ctx: Any,
    verifier: Any | None,
    sip_owner_numbers: Iterable[str] = (),
) -> tuple[Callable[[], bool], OwnerGate]:
    gate = OwnerGate(ctx, verifier, sip_owner_numbers=sip_owner_numbers)
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
