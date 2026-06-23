"""Scorecard data model + composite scoring for the Samuel benchmark.

Mirrors ``sam-benchmark-methodology.md`` sections 3-4. Pure functions + dataclasses so the math is
unit-testable without any live pipeline. Latency is reported as p50/p90/p95; quality metrics are
normalized to 0..1 before weighting.

Two arenas:
- General arena (table stakes): latency, barge-in, naturalness, recovery/charm.
- Grounded arena (the product KPI): task success, (1 - hallucination), tool accuracy, refusal.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (matches harness.py's convention)."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int((p / 100.0) * len(s)))
    return s[idx]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


@dataclass
class LatencyStats:
    """Voice-to-voice latency samples (ms) for one arm/scenario."""

    v2v_ms: list[float] = field(default_factory=list)

    @property
    def p50(self) -> float:
        return percentile(self.v2v_ms, 50)

    @property
    def p90(self) -> float:
        return percentile(self.v2v_ms, 90)

    @property
    def p95(self) -> float:
        return percentile(self.v2v_ms, 95)

    def latency_score(self, *, good_ms: float = 800.0, bad_ms: float = 1500.0) -> float:
        """1.0 at/under the 800ms KPI (ADR-8), 0.0 at/over 1500ms, linear between (uses p50).

        No samples => 0.0 (absence of data is not a passing score).
        """
        if not self.v2v_ms:
            return 0.0
        if bad_ms <= good_ms:
            return 1.0 if self.p50 <= good_ms else 0.0
        return _clamp01((bad_ms - self.p50) / (bad_ms - good_ms))

    def passes_kpi(self) -> bool:
        """ADR-8 gate: v2v <= 800ms p50 and <= 1500ms p95. No samples => not passing."""
        if not self.v2v_ms:
            return False
        return self.p50 <= 800.0 and self.p95 <= 1500.0


@dataclass
class GeneralArena:
    """Table-stakes interaction quality (level playing field vs a general voice agent)."""

    latency: LatencyStats = field(default_factory=LatencyStats)
    barge_in_f1: float = 0.0          # F1 of true-interrupt detection (0..1)
    naturalness_mos: float = 0.0      # ITU-T MOS 1..5
    recovery_charm: float = 0.0       # rubric normalized 0..1

    def score(self) -> float:
        return general_arena_score(self)


@dataclass
class GroundedArena:
    """The arena that matters: can the agent act correctly on the user's real data."""

    task_success_rate: float = 0.0     # 0..1
    hallucination_rate: float = 0.0    # 0..1 (lower is better)
    tool_call_accuracy: float = 0.0    # 0..1
    refusal_appropriateness: float = 0.0  # 0..1

    def score(self) -> float:
        return grounded_arena_score(self)


def general_arena_score(a: GeneralArena) -> float:
    return round(
        0.35 * _clamp01(a.latency.latency_score())
        + 0.25 * _clamp01(a.barge_in_f1)
        + 0.25 * _clamp01(a.naturalness_mos / 5.0)
        + 0.15 * _clamp01(a.recovery_charm),
        4,
    )


def grounded_arena_score(g: GroundedArena) -> float:
    return round(
        0.45 * _clamp01(g.task_success_rate)
        + 0.30 * _clamp01(1.0 - g.hallucination_rate)
        + 0.15 * _clamp01(g.tool_call_accuracy)
        + 0.10 * _clamp01(g.refusal_appropriateness),
        4,
    )


@dataclass
class RunScorecard:
    """One full benchmark run for one arm (e.g. 'samuel', 'chatgpt-voice')."""

    arm: str
    method_version: str = "0.1.0"
    network_profile: str = "wifi"
    region: str = "unknown"
    n_turns: int = 0
    general: GeneralArena = field(default_factory=GeneralArena)
    grounded: GroundedArena = field(default_factory=GroundedArena)
    notes: str = ""

    def summary(self) -> dict:
        return {
            "arm": self.arm,
            "method_version": self.method_version,
            "network_profile": self.network_profile,
            "region": self.region,
            "n_turns": self.n_turns,
            "latency_p50_ms": round(self.general.latency.p50, 1),
            "latency_p95_ms": round(self.general.latency.p95, 1),
            "passes_latency_kpi": self.general.latency.passes_kpi(),
            "general_arena_score": self.general.score(),
            "grounded_arena_score": self.grounded.score(),
            "hallucination_rate": self.grounded.hallucination_rate,
            "notes": self.notes,
        }
