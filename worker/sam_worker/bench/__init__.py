"""Samuel benchmark harness (scaffold).

Implements the scorecard defined in
``rainMaker/studios/research/sam-benchmark-methodology.md``: a two-arena, percentile-reported,
reproducible comparison vs ChatGPT Advanced Voice.

This package is **scaffold only** -- the scorecard data model + composite math are real and
unit-tested, but the live arms (driving Samuel / ChatGPT voice end to end) are intentionally not
run here. Wire them after Wave 1 (Hermes brain + read-only tools) makes the grounded arena real.

Entry points:
- ``scorecard``  : metric containers + composite scoring (pure, testable now).
- ``fixtures``   : the versioned task/interruption suites (ground-truth backed).
- ``bench_config.json`` : the arms (samuel / samuel-groq / chatgpt-voice / samuel-s2s).
"""

from .scorecard import (
    GroundedArena,
    LatencyStats,
    RunScorecard,
    grounded_arena_score,
    general_arena_score,
    percentile,
)

__all__ = [
    "LatencyStats",
    "GroundedArena",
    "RunScorecard",
    "percentile",
    "general_arena_score",
    "grounded_arena_score",
]
