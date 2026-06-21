"""Hermes brain client — OpenAI-compatible chat-completions (streaming).

This mirrors rm_api's ask_charles() bridge: same brain, reached over the network. The tier
selects the model (see config.model_for_tier). Phase 4 ships a MockBrain; the real streaming
client is a thin httpx wrapper added in Phase 5.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol


class Brain(Protocol):
    async def stream(self, prompt: str, *, model: str, history: list[dict]) -> AsyncIterator[str]:
        ...


class MockBrain:
    """Deterministic-ish fake that streams a short reply token-by-token with realistic TTFT."""

    async def stream(
        self, prompt: str, *, model: str, history: list[dict]
    ) -> AsyncIterator[str]:
        await asyncio.sleep(0.25)  # simulate TTFT
        reply = f"[{model}] Got it — {prompt.strip()[:60]}. Here's the quick read."
        for word in reply.split(" "):
            await asyncio.sleep(0.02)
            yield word + " "


class HermesBrain:
    """Real client — STUB for Phase 5.

    Wire to HERMES_BASE_URL `/v1/chat/completions` with stream=True via httpx, passing the
    tier-selected `model`. Assemble messages from the tier-trimmed `history` + persona system
    hint. Yield content deltas as they arrive so TTS can start on the first sentence.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    async def stream(
        self, prompt: str, *, model: str, history: list[dict]
    ) -> AsyncIterator[str]:
        raise NotImplementedError("HermesBrain is a Phase 5 stub; use MockBrain in --mock.")
        # pragma: no cover
        yield ""  # keeps the type checker happy that this is an async generator
