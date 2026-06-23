"""Tests for the benchmark scorecard math (scaffold)."""

from __future__ import annotations

from sam_worker.bench.scorecard import (
    GeneralArena,
    GroundedArena,
    LatencyStats,
    RunScorecard,
    general_arena_score,
    grounded_arena_score,
    percentile,
)
from sam_worker.bench.fixtures import GROUNDED_TASKS, fixture_manifest


def test_percentile_nearest_rank() -> None:
    vals = [100.0, 200.0, 300.0, 400.0, 500.0]
    assert percentile(vals, 50) == 300.0
    assert percentile([], 50) == 0.0


def test_latency_score_and_kpi_gate() -> None:
    good = LatencyStats(v2v_ms=[600, 650, 700, 750])  # all under 800
    assert good.latency_score() == 1.0
    assert good.passes_kpi() is True

    over = LatencyStats(v2v_ms=[1091] * 10)  # current p50 ~1091ms
    assert 0.0 < over.latency_score() < 1.0
    assert over.passes_kpi() is False

    broken = LatencyStats(v2v_ms=[1600] * 5)
    assert broken.latency_score() == 0.0


def test_general_arena_score_bounds() -> None:
    a = GeneralArena(
        latency=LatencyStats(v2v_ms=[700] * 5),
        barge_in_f1=1.0,
        naturalness_mos=5.0,
        recovery_charm=1.0,
    )
    assert general_arena_score(a) == 1.0

    empty = GeneralArena()
    assert general_arena_score(empty) == 0.0


def test_grounded_arena_rewards_low_hallucination() -> None:
    perfect = GroundedArena(
        task_success_rate=1.0,
        hallucination_rate=0.0,
        tool_call_accuracy=1.0,
        refusal_appropriateness=1.0,
    )
    assert grounded_arena_score(perfect) == 1.0

    # Same task success but high hallucination must score materially lower.
    hallucinating = GroundedArena(
        task_success_rate=1.0,
        hallucination_rate=1.0,
        tool_call_accuracy=1.0,
        refusal_appropriateness=1.0,
    )
    assert grounded_arena_score(hallucinating) < grounded_arena_score(perfect)
    assert grounded_arena_score(hallucinating) == round(0.45 + 0.15 + 0.10, 4)


def test_run_scorecard_summary_shape() -> None:
    sc = RunScorecard(arm="samuel-groq", n_turns=30)
    sc.general.latency = LatencyStats(v2v_ms=[1091] * 30)
    out = sc.summary()
    assert out["arm"] == "samuel-groq"
    assert out["passes_latency_kpi"] is False
    assert "grounded_arena_score" in out


def test_fixtures_have_hallucination_traps() -> None:
    # The pricing/account traps must exist and forbid invented numbers.
    ids = {t.id for t in GROUNDED_TASKS}
    assert {"pricing_trap", "account_trap"} <= ids
    assert fixture_manifest()["version"]
