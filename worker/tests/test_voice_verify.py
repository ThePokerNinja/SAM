"""Owner voice-gate: VoiceVerifier config-guarding + recency/threshold, and the
access-key participant fallback. No Picovoice dependency required (Eagle is faked)."""

from __future__ import annotations

import time
import unittest

from sam_worker.agent import _participant_is_owner
from sam_worker.config import Settings
from sam_worker.voice_verify import VoiceVerifier


class _FakeEagle:
    frame_length = 512

    def process(self, _pcm):  # pragma: no cover - not exercised here
        return [0.0]


class FromSettingsGuardTests(unittest.TestCase):
    def test_none_without_access_key(self) -> None:
        s = Settings(picovoice_access_key="", owner_voiceprint="deadbeef")
        self.assertIsNone(VoiceVerifier.from_settings(s))

    def test_none_with_key_but_no_voiceprint(self) -> None:
        s = Settings(picovoice_access_key="pk", owner_voiceprint="", owner_voiceprint_path="")
        self.assertIsNone(VoiceVerifier.from_settings(s))


class RecencyThresholdTests(unittest.TestCase):
    def _v(self, threshold=0.5) -> VoiceVerifier:
        return VoiceVerifier(_FakeEagle(), profile=None, threshold=threshold, recency_s=5.0)

    def test_not_owner_before_any_score(self) -> None:
        self.assertFalse(self._v().is_owner())

    def test_owner_when_fresh_and_above_threshold(self) -> None:
        v = self._v(threshold=0.5)
        v._score = 0.8
        v._score_at = time.time()
        self.assertTrue(v.is_owner())

    def test_not_owner_when_below_threshold(self) -> None:
        v = self._v(threshold=0.5)
        v._score = 0.3
        v._score_at = time.time()
        self.assertFalse(v.is_owner())

    def test_not_owner_when_stale(self) -> None:
        v = self._v(threshold=0.5)
        v._score = 0.9
        v._score_at = time.time() - 100.0  # outside recency window
        self.assertFalse(v.is_owner())


class _FakeP:
    def __init__(self, attrs):
        self.attributes = attrs


class _FakeRoom:
    def __init__(self, participants):
        self.remote_participants = {i: p for i, p in enumerate(participants)}


class _FakeCtx:
    def __init__(self, participants):
        self.room = _FakeRoom(participants)


class ParticipantOwnerFallbackTests(unittest.TestCase):
    def test_owner_attribute_recognized(self) -> None:
        ctx = _FakeCtx([_FakeP({"role": "owner"})])
        self.assertTrue(_participant_is_owner(ctx))

    def test_no_owner_attribute(self) -> None:
        ctx = _FakeCtx([_FakeP({}), _FakeP({"role": "guest"})])
        self.assertFalse(_participant_is_owner(ctx))

    def test_empty_room(self) -> None:
        self.assertFalse(_participant_is_owner(_FakeCtx([])))


if __name__ == "__main__":
    unittest.main()
