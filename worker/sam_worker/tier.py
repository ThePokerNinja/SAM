"""Server-side half of the tier system: the client reports its current tier over the LiveKit
data channel; the worker applies the brain model + memory depth for the next turn (ADR-7).

Visual/voice-richness are applied client/TTS-side; here we only touch brain + memory, and only
at turn boundaries (never mid-utterance)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import memory_turns_for_tier, model_for_tier


@dataclass
class TierState:
    tier: int = 2

    @property
    def model(self) -> str:
        return model_for_tier(self.tier)

    @property
    def memory_turns(self) -> int:
        return memory_turns_for_tier(self.tier)

    def update(self, tier: int) -> bool:
        """Apply a new tier reported by the client. Returns True if it changed."""
        tier = max(0, min(4, int(tier)))
        if tier == self.tier:
            return False
        self.tier = tier
        return True

    def trim_history(self, history: list[dict]) -> list[dict]:
        n = self.memory_turns
        return history[-n:] if n and len(history) > n else history
