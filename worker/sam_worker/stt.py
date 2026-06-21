"""STT stage — Deepgram Nova-3 streaming (ADR-3). Phase 4 = stub notes only.

Phase 5: use livekit-plugins-deepgram with streaming partials; the LiveKit AgentSession
consumes this directly. Configure a fallback STT provider per ADR-3.
"""

from __future__ import annotations


def build_stt(deepgram_api_key: str):  # -> deepgram.STT (Phase 5)
    """Return a configured Deepgram streaming STT. Stubbed until Phase 5."""
    raise NotImplementedError(
        "STT wiring is Phase 5. In --mock the turn loop simulates transcripts."
    )
