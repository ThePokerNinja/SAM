"""Owner gate: attribute cache, portal fallback when voice verify is off."""

from __future__ import annotations

import unittest

from sam_worker.config import Settings
from sam_worker.owner_gate import OwnerGate, participant_has_owner_role
from sam_worker.voice_verify import VoiceVerifier


class _FakeP:
    def __init__(self, attrs=None):
        self.attributes = attrs or {}


class _FakeRoom:
    def __init__(self, participants):
        self.remote_participants = {i: p for i, p in enumerate(participants)}


class _FakeCtx:
    def __init__(self, participants):
        self.room = _FakeRoom(participants)


class ParticipantOwnerRoleTests(unittest.TestCase):
    def test_owner_attribute_recognized(self) -> None:
        ctx = _FakeCtx([_FakeP({"role": "owner"})])
        self.assertTrue(participant_has_owner_role(ctx))

    def test_no_owner_attribute(self) -> None:
        ctx = _FakeCtx([_FakeP({})])
        self.assertFalse(participant_has_owner_role(ctx))


class OwnerGateTests(unittest.TestCase):
    def test_portal_fallback_when_voice_verify_off(self) -> None:
        ctx = _FakeCtx([_FakeP({})])  # no role attr - common prod bug
        gate = OwnerGate(ctx, verifier=None)
        self.assertTrue(gate.is_owner())

    def test_no_portal_fallback_when_voice_verify_armed(self) -> None:
        ctx = _FakeCtx([_FakeP({})])
        gate = OwnerGate(ctx, verifier=object())  # armed but no is_owner method -> fails
        # Monkey-patch minimal verifier that never matches
        gate._verifier = type("V", (), {"is_owner": lambda self: False})()
        self.assertFalse(gate.is_owner())

    def test_attribute_cached_on_connect(self) -> None:
        ctx = _FakeCtx([])
        gate = OwnerGate(ctx, verifier=None)
        gate.on_participant_connected(_FakeP({"role": "owner"}))
        self.assertTrue(gate.is_owner())

    def test_voice_match_wins_when_armed(self) -> None:
        ctx = _FakeCtx([])
        gate = OwnerGate(ctx, verifier=type("V", (), {"is_owner": lambda self: True})())
        self.assertTrue(gate.is_owner())


class FromSettingsGuardTests(unittest.TestCase):
    def test_none_without_access_key(self) -> None:
        s = Settings(picovoice_access_key="", owner_voiceprint="deadbeef")
        self.assertIsNone(VoiceVerifier.from_settings(s))


if __name__ == "__main__":
    unittest.main()
