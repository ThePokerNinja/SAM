from __future__ import annotations

from sam_worker.bench.evaluation import TaskObservation, evaluate_observations
from sam_worker.bench.fixtures import GROUNDED_TASKS
from sam_worker.skillbuilder.models import (
    AlignmentInputs,
    ConfidenceInputs,
    ExpectedLift,
    KPISnapshot,
    RiskInputs,
    SkillCandidate,
)
from sam_worker.skillbuilder.runtime import SkillBuilderRuntime
from sam_worker.skillbuilder.snapshot import live_snapshot
from sam_worker.skillbuilder.states import CandidateStatus


def _strong_candidate() -> SkillCandidate:
    return SkillCandidate(
        candidate_id="candidate-1",
        skill_name="Fast grounded lookup",
        expected_lift=ExpectedLift(0.9, 0.9, 0.9, 0.9, 0.9),
        alignment=AlignmentInputs(0.95, 0.95, 0.95, 0.95, 0.95),
        risk=RiskInputs(0.05, 0.05, 0.05, 0.05, 0.05, 0.05),
        confidence=ConfidenceInputs(0.95, 0.95, 0.95),
        static_urgency=0.9,
        fits_latency_budget=True,
    )


def test_kpis_persist_and_latest_wins(tmp_path) -> None:
    runtime = SkillBuilderRuntime(tmp_path / "skills.db")
    runtime.record_kpi("trading", KPISnapshot("task_success", 0.8))
    runtime.record_kpi("trading", KPISnapshot("task_success", 0.95))
    runtime.record_kpi("trading", KPISnapshot("v2v_p50_ms", 740.0))
    current = SkillBuilderRuntime(tmp_path / "skills.db").latest_kpis("trading")
    assert current["task_success"].metric_value == 0.95
    assert current["v2v_p50_ms"].metric_value == 740.0


def test_live_snapshot_uses_measured_session_latency(tmp_path) -> None:
    runtime = SkillBuilderRuntime(tmp_path / "skills.db")
    runtime.record_kpi("samuel_live_session", KPISnapshot("v2v_ms", 600.0))
    runtime.record_kpi("samuel_live_session", KPISnapshot("v2v_ms", 1000.0))
    runtime.record_kpi("samuel_live_session", KPISnapshot("v2v_ms", 800.0))
    snapshot = live_snapshot(runtime)
    assert snapshot["attributes"]["reflexes"] == 100


def test_adoption_is_default_deny_until_explicit_consent(tmp_path) -> None:
    runtime = SkillBuilderRuntime(tmp_path / "skills.db")
    candidate = runtime.approve_for_implementation(_strong_candidate())
    assert candidate.status == CandidateStatus.UNDER_REVIEW
    runtime.record_consent(
        candidate.candidate_id,
        approved=True,
        decided_by="owner",
        evidence_ref="rm_api:approval:ABC123",
    )
    candidate = runtime.approve_for_implementation(candidate)
    assert candidate.status == CandidateStatus.APPROVED


def test_denied_consent_never_promotes(tmp_path) -> None:
    runtime = SkillBuilderRuntime(tmp_path / "skills.db")
    candidate = _strong_candidate()
    runtime.record_consent(
        candidate.candidate_id,
        approved=False,
        decided_by="owner",
        evidence_ref="rm_api:approval:NO123",
    )
    assert runtime.approve_for_implementation(candidate).status == CandidateStatus.UNDER_REVIEW


def test_intelligence_report_uses_existing_two_arena_scorecard() -> None:
    observations = [
        TaskObservation(
            fixture_id=fixture.id,
            response="grounded",
            tool_called=fixture.expected_tool,
            task_succeeded=True,
        )
        for fixture in GROUNDED_TASKS
    ]
    report = evaluate_observations(
        observations,
        v2v_ms=[700.0, 750.0],
        barge_in_f1=1.0,
        interruption_accuracy=1.0,
        learning_efficiency=0.8,
    )
    summary = report.summary()
    assert summary["grounded_arena_score"] == 1.0
    assert summary["passes_latency_kpi"] is True
    assert summary["intent_accuracy"] == 1.0
    assert summary["learning_efficiency"] == 0.8
    assert summary["failures"] == []


def test_intelligence_report_fails_closed_on_missing_fixture() -> None:
    report = evaluate_observations([])
    assert len(report.failures) == len(GROUNDED_TASKS)
    assert report.scorecard.grounded.score() < 1.0


def test_intelligence_report_marks_empty_observation_unscored() -> None:
    fixture = GROUNDED_TASKS[0]
    report = evaluate_observations(
        [
            TaskObservation(
                fixture_id=fixture.id,
                response="",
                tool_called=fixture.expected_tool,
                task_succeeded=False,
            )
        ]
    )
    assert f"unscored:{fixture.id}" in report.failures
