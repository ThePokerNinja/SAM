"""Owner voice verification (Tier-T gate) via Picovoice Eagle.

The owner's voice IS Samuel's cloned TTS voice, so two rules are non-negotiable:
  1. We only ever score the REMOTE human mic track - never Samuel's own audio - so the
     agent can't self-authenticate by speaking in the owner's voice.
  2. Voice is never the sole gate for money (trades keep the SMS code consent). This
     module only unlocks Tier-T triggers (run scan, queue research).

The whole feature is inert unless BOTH a Picovoice access key and an enrolled owner
voiceprint are configured. With either missing, `from_settings` returns None and the
caller falls back to the access-key owner attribute. This keeps local dev + CI green
with no Picovoice dependency installed.
"""

from __future__ import annotations

import array
import base64
import logging
import time
from typing import Any

_log = logging.getLogger("sam.voice_verify")

# Eagle operates on 16 kHz mono 16-bit PCM.
_EAGLE_RATE = 16000


def _load_profile_bytes(s: Any) -> bytes | None:
    raw_b64 = (getattr(s, "owner_voiceprint", "") or "").strip()
    if raw_b64:
        try:
            return base64.b64decode(raw_b64)
        except Exception:  # noqa: BLE001
            _log.warning("owner voiceprint base64 is invalid; ignoring")
    path = (getattr(s, "owner_voiceprint_path", "") or "").strip()
    if path:
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError as exc:
            _log.warning("owner voiceprint path unreadable: %s", exc)
    return None


class VoiceVerifier:
    """Rolling owner-confidence from the human mic, scored by Eagle.

    `attach(room)` subscribes to the remote participant's audio and feeds resampled
    frames into Eagle. `is_owner()` reports whether a fresh, high-enough score was seen
    recently. Construction never raises - failures degrade to "not verified".
    """

    def __init__(self, eagle: Any, profile: Any, *, threshold: float, recency_s: float = 6.0) -> None:
        self._eagle = eagle
        self._profile = profile
        self._threshold = threshold
        self._recency_s = recency_s
        self._score = 0.0
        self._score_at = 0.0
        self._buf = array.array("h")  # int16 accumulator until eagle.frame_length
        self._frame_length = int(getattr(eagle, "frame_length", 0) or 0)
        self._resampler: Any = None
        self._attached = False

    @classmethod
    def from_settings(cls, s: Any) -> "VoiceVerifier | None":
        key = (getattr(s, "picovoice_access_key", "") or "").strip()
        if not key:
            return None
        profile_bytes = _load_profile_bytes(s)
        if not profile_bytes:
            _log.info("voice verify: access key present but no owner voiceprint - gate disabled")
            return None
        try:
            import pveagle  # type: ignore

            profile = pveagle.EagleProfile.from_bytes(profile_bytes)
            eagle = pveagle.create_recognizer(access_key=key, speaker_profiles=[profile])
        except Exception as exc:  # noqa: BLE001 - any failure leaves the gate on the fallback
            _log.warning("voice verify: Eagle init failed (%s); gate falls back to access-key", exc)
            return None
        thr = float(getattr(s, "voice_threshold", 0.5) or 0.5)
        _log.info("voice verify: Eagle recognizer ready (threshold=%.2f)", thr)
        return cls(eagle, profile, threshold=thr)

    # -- runtime --------------------------------------------------------------

    def is_owner(self) -> bool:
        """True when a score >= threshold was observed within the recency window."""
        if (time.time() - self._score_at) > self._recency_s:
            return False
        return self._score >= self._threshold

    @property
    def last_score(self) -> float:
        return self._score

    def attach(self, room: Any) -> None:
        """Wire the remote human mic into the recognizer. Idempotent and defensive."""
        if self._attached:
            return
        self._attached = True
        try:
            import asyncio

            import livekit.rtc as rtc
        except Exception as exc:  # noqa: BLE001
            _log.warning("voice verify: livekit.rtc unavailable (%s)", exc)
            return

        @room.on("track_subscribed")
        def _on_track(track: Any, _pub: Any, _participant: Any) -> None:
            # Only remote participants are subscribed, so this is always the human mic;
            # Samuel's own TTS is a locally-published track and never arrives here.
            if getattr(track, "kind", None) != rtc.TrackKind.KIND_AUDIO:
                return
            asyncio.ensure_future(self._consume(track, rtc))

        # Catch any audio track that subscribed before we attached.
        try:
            for participant in room.remote_participants.values():
                for pub in participant.track_publications.values():
                    track = getattr(pub, "track", None)
                    if track is not None and getattr(track, "kind", None) == rtc.TrackKind.KIND_AUDIO:
                        asyncio.ensure_future(self._consume(track, rtc))
        except Exception as exc:  # noqa: BLE001
            _log.debug("voice verify: existing-track scan skipped (%s)", exc)

    async def _consume(self, track: Any, rtc: Any) -> None:
        try:
            stream = rtc.AudioStream(track)
            async for ev in stream:
                frame = getattr(ev, "frame", None)
                if frame is None:
                    continue
                self._on_frame(frame, rtc)
        except Exception as exc:  # noqa: BLE001 - never let audio plumbing crash the session
            _log.debug("voice verify: consume loop ended (%s)", exc)

    def _on_frame(self, frame: Any, rtc: Any) -> None:
        if self._frame_length <= 0:
            return
        try:
            if self._resampler is None:
                self._resampler = rtc.AudioResampler(
                    input_rate=frame.sample_rate,
                    output_rate=_EAGLE_RATE,
                    num_channels=1,
                )
            for resampled in self._resampler.push(frame):
                self._buf.frombytes(bytes(resampled.data))
            while len(self._buf) >= self._frame_length:
                chunk = self._buf[: self._frame_length]
                del self._buf[: self._frame_length]
                scores = self._eagle.process(list(chunk))
                if scores:
                    self._score = float(scores[0])
                    self._score_at = time.time()
        except Exception as exc:  # noqa: BLE001
            _log.debug("voice verify: frame scoring skipped (%s)", exc)
