"""Deterministic Wave 8 intelligence evaluation over versioned fixtures (SAM-067)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .fixtures import GROUNDED_TASKS, GroundedTask
from .scorecard import GeneralArena, GroundedArena, LatencyStats, RunScorecard


@dataclass(frozen=True)
class TaskObservation:
    fixture_id: str
    response: str
    tool_called: str | None
    task_succeeded: bool
    hallucinated: bool = False
    refusal_appropriate: bool = True
    intent_correct: bool = True
    context_retained: bool = True


@dataclass
class IntelligenceReport:
    scorecard: RunScorecard
    intent_accuracy: float
    context_retention_rate: float
    interruption_accuracy: float
    learning_efficiency: float | None = None
    failures: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            **self.scorecard.summary(),
            "intent_accuracy": round(self.intent_accuracy, 4),
            "context_retention_rate": round(self.context_retention_rate, 4),
            "interruption_accuracy": round(self.interruption_accuracy, 4),
            "learning_efficiency": (
                round(self.learning_efficiency, 4)
                if self.learning_efficiency is not None
                else None
            ),
            "failures": self.failures,
        }


def evaluate_observations(
    observations: list[TaskObservation],
    *,
    v2v_ms: list[float] | None = None,
    barge_in_f1: float = 0.0,
    interruption_accuracy: float = 0.0,
    naturalness_mos: float = 0.0,
    recovery_charm: float = 0.0,
    learning_efficiency: float | None = None,
    arm: str = "samuel",
) -> IntelligenceReport:
    expected = {fixture.id: fixture for fixture in GROUNDED_TASKS}
    observed = {row.fixture_id: row for row in observations}
    failures: list[str] = []

    for fixture_id in expected:
        if fixture_id not in observed:
            failures.append(f"missing:{fixture_id}")
    for fixture_id in observed:
        if fixture_id not in expected:
            failures.append(f"unknown:{fixture_id}")

    rows = [observed[key] for key in expected if key in observed]
    for row in rows:
        if not row.response.strip():
            failures.append(f"unscored:{row.fixture_id}")
    count = len(rows)

    def rate(predicate) -> float:
        return sum(1 for row in rows if predicate(row)) / count if count else 0.0

    tool_accuracy = rate(
        lambda row: row.tool_called == expected[row.fixture_id].expected_tool
    )
    grounded = GroundedArena(
        task_success_rate=rate(lambda row: row.task_succeeded),
        hallucination_rate=rate(lambda row: row.hallucinated),
        tool_call_accuracy=tool_accuracy,
        refusal_appropriateness=rate(lambda row: row.refusal_appropriate),
    )
    general = GeneralArena(
        latency=LatencyStats(v2v_ms or []),
        barge_in_f1=barge_in_f1,
        naturalness_mos=naturalness_mos,
        recovery_charm=recovery_charm,
    )
    scorecard = RunScorecard(
        arm=arm,
        n_turns=count,
        general=general,
        grounded=grounded,
        notes="Wave 8 deterministic fixture evaluation",
    )
    return IntelligenceReport(
        scorecard=scorecard,
        intent_accuracy=rate(lambda row: row.intent_correct),
        context_retention_rate=rate(lambda row: row.context_retained),
        interruption_accuracy=interruption_accuracy,
        learning_efficiency=learning_efficiency,
        failures=failures,
    )


def load_observations(path: Path | str) -> list[TaskObservation]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("observations", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TypeError("observation file must contain a list")
    return [TaskObservation(**row) for row in rows]


def expected_fixture(fixture_id: str) -> GroundedTask:
    for fixture in GROUNDED_TASKS:
        if fixture.id == fixture_id:
            return fixture
    raise KeyError(fixture_id)
