"""TTS stage — ElevenLabs Flash v2.5 over WebSocket (ADR-4). Phase 4 = stub notes only.

Phase 5: use livekit-plugins-elevenlabs with model `eleven_flash_v2_5`, flush:true / auto_mode,
and per-persona voice_id. Tier sets ttsSettings (high/default/low_latency). v3 is used only for
the pre-rendered Lite demo, not this live path.
"""

from __future__ import annotations

from .config import Settings


def voice_id_for(persona_id: str, settings: Settings) -> str:
    return settings.voice_ids.get(persona_id, "") or settings.voice_ids.get("samuel", "")


def build_tts(persona_id: str, settings: Settings, tier: int):  # -> elevenlabs.TTS (Phase 5)
    """Return a configured ElevenLabs streaming TTS for a persona at a tier. Stubbed."""
    raise NotImplementedError(
        "TTS wiring is Phase 5. In --mock the turn loop simulates synthesis timing."
    )
