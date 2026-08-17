"""Turn handling configuration for the Wave 8 experiment matrix."""

from __future__ import annotations

from typing import Any

from livekit.agents import inference

from .config import Settings


def build_turn_handling(settings: Settings) -> dict[str, Any]:
    """Build the non-deprecated LiveKit ``TurnHandlingOptions`` mapping.

    ``cloud`` lets LiveKit select v1 where eligible and fall back to v1-mini
    for self-hosted workers. ``mini`` pins the local model. VAD and STT use the
    framework's built-in low-latency modes.
    """
    if settings.endpoint_min < 0 or settings.endpoint_max < settings.endpoint_min:
        raise ValueError("endpoint delays must satisfy 0 <= min <= max")

    mode = settings.turn_mode
    if mode == "cloud":
        detector: Any = inference.TurnDetector(local_fallback=True)
    elif mode == "mini":
        detector = inference.TurnDetector(version="v1-mini", local_fallback=True)
    else:
        detector = mode

    endpointing = (
        {
            "mode": "fixed",
            "min_delay": 0.0,
        }
        if mode == "stt"
        else {
            "mode": "dynamic",
            "min_delay": settings.endpoint_min,
            "max_delay": settings.endpoint_max,
        }
    )

    return {
        "turn_detection": detector,
        # STT-native end-of-turn already includes the provider's endpointing
        # delay. Any LiveKit min_delay is additive, while max_delay is ignored.
        "endpointing": endpointing,
        "interruption": {
            "enabled": True,
            "mode": settings.interruption_mode,
            "min_duration": settings.interruption_min_duration,
            "min_words": settings.interruption_min_words,
            "resume_false_interruption": True,
            "false_interruption_timeout": 1.0,
            "backchannel_boundary": (0.6, 0.6),
        },
        "preemptive_generation": {
            "enabled": True,
            "preemptive_tts": settings.preemptive_tts,
            "max_speech_duration": 10.0,
            "max_retries": 3,
        },
    }
