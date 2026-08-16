"""Samuel benchmark harness.

Implements the scorecard defined in
``rainMaker/studios/research/sam-benchmark-methodology.md``: a two-arena, percentile-reported,
reproducible comparison vs ChatGPT Advanced Voice.

The Samuel LiveKit arm is automated end to end with deterministic synthetic speech. The ChatGPT
Voice comparison remains disabled and must respect the provider's terms.

Entry points:
- ``scorecard``  : metric containers + composite scoring (pure, testable now).
- ``fixtures``   : the versioned task/interruption suites (ground-truth backed).
- ``livekit_audio`` : external full-audio driver for latency and barge-in.
- ``evaluation`` : deterministic intelligence report over the existing two-arena scorecard.
- ``bench_config.json`` : the arms (samuel / samuel-groq / chatgpt-voice / samuel-s2s).
"""

from .scorecard import (
    GroundedArena,
    LatencyStats,
    RunScorecard,
    general_arena_score,
    grounded_arena_score,
    percentile,
)

__all__ = [
    "GroundedArena",
    "LatencyStats",
    "RunScorecard",
    "general_arena_score",
    "grounded_arena_score",
    "percentile",
]
