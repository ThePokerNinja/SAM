"""Tests for the benchmark scorecard math (scaffold)."""

from __future__ import annotations

from sam_worker.bench.scorecard import (
    DuplexArena,
    GeneralArena,
    GroundedArena,
    LatencyStats,
    RunScorecard,
    duplex_arena_score,
    general_arena_complete,
    general_arena_has_naturalness,
    general_arena_score,
    grounded_arena_score,
    percentile,
)
from sam_worker.bench.fixtures import DUPLEX_CASES, GROUNDED_TASKS, INTERRUPTIONS, fixture_manifest


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

    p95_miss = LatencyStats(v2v_ms=[700] * 19 + [1300])
    assert p95_miss.p50 < 800
    assert p95_miss.passes_kpi() is False

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
    assert general_arena_has_naturalness(a) is True
    assert general_arena_complete(a) is True

    empty = GeneralArena()
    assert general_arena_score(empty) == 0.0
    assert general_arena_has_naturalness(empty) is False
    assert general_arena_complete(empty) is False

    no_mos = GeneralArena(
        latency=LatencyStats(v2v_ms=[700] * 5),
        barge_in_f1=1.0,
        naturalness_mos=0.0,
    )
    assert general_arena_score(no_mos) == 0.0


def test_duplex_arena_score_bounds() -> None:
    perfect = DuplexArena(
        pause_respect_rate=1.0,
        backchannel_f1=1.0,
        truncation_correct_rate=1.0,
        participate_score=1.0,
        side_speech_false_trigger_rate=0.0,
    )
    assert duplex_arena_score(perfect) == 1.0
    assert duplex_arena_score(DuplexArena()) == 0.0


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
    manifest = fixture_manifest()
    assert manifest["version"]
    assert len(manifest["duplex_cases"]) >= 8
    assert any(c.expect_context_reset for c in INTERRUPTIONS)
    assert any(c.id == "barge_in_truncate" for c in DUPLEX_CASES)
