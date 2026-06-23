"""STT stage — Deepgram Nova-3 streaming (ADR-3).

Default prod path uses LiveKit Inference (no Deepgram key). When ``DEEPGRAM_API_KEY`` is set,
or ``SAM_STT=deepgram``, we use the Deepgram plugin directly — bypasses LiveKit Inference
rate limits (429) on ``agent-gateway.livekit.cloud``.
"""

from __future__ import annotations

import os

from livekit.agents import inference
from livekit.plugins import deepgram

from .config import Settings


def build_stt(s: Settings):
    """Return STT for AgentSession: Deepgram direct when configured, else LiveKit Inference."""
    mode = (os.getenv("SAM_STT", "") or "").strip().lower()
    use_deepgram = mode == "deepgram" or (mode != "inference" and bool(s.deepgram_api_key))

    if use_deepgram:
        if not s.deepgram_api_key:
            raise RuntimeError("SAM_STT=deepgram but DEEPGRAM_API_KEY is not set in worker/.env")
        model = s.stt_model.removeprefix("deepgram/") if s.stt_model.startswith("deepgram/") else "nova-3"
        return deepgram.STT(model=model, api_key=s.deepgram_api_key)

    return inference.STT(model=s.stt_model)
