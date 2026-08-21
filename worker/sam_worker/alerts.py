"""Named failure classes + burst detection for owner SMS alerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GROQ_429 = "groq_429_burst"
LLM_FALLBACK = "llm_fallback_exhausted"
BARGE_CARRIER = "barge_in_carrier_miss"
FAILURE_CLASSES = (GROQ_429, LLM_FALLBACK, BARGE_CARRIER)


@dataclass
class BurstTracker:
    """Count events in a rolling window; fire once per window."""

    window_s: float = 600.0
    threshold: int = 3
    count: int = 0
    window_start: float = 0.0
    alerted: bool = False
    events: list[float] = field(default_factory=list)

    def observe(self, now: float, *, is_match: bool) -> bool:
        """Return True the first time the burst crosses the threshold."""
        if not is_match:
            return False
        if now - self.window_start > self.window_s:
            self.count = 0
            self.window_start = now
            self.alerted = False
        self.count += 1
        self.events.append(now)
        if self.count >= self.threshold and not self.alerted:
            self.alerted = True
            return True
        return False
