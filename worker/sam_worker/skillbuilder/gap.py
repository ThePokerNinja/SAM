"""Turn a closed session into a SkillCandidate when a measurable gap exists."""

from __future__ import annotations

from .models import (
    AlignmentInputs,
    ConfidenceInputs,
    ExpectedLift,
    RiskInputs,
    SkillCandidate,
)


def candidate_from_latency(
    session_id: str,
    *,
    v2v_p50_ms: float,
    threshold_ms: float = 800.0,
) -> SkillCandidate | None:
    if v2v_p50_ms <= threshold_ms:
        return None
    return SkillCandidate(
        candidate_id=f"latency-{session_id[:12]}",
        skill_name="conversational_latency_polish",
        problem_detected=f"session v2v p50 {v2v_p50_ms:.0f}ms over {threshold_ms:.0f}ms",
        trigger_metric="v2v_p50_ms",
        expected_lift=ExpectedLift(
            efficiency=0.95,
            satisfaction=0.95,
            scalability=0.9,
            retention=0.8,
            revenue=0.6,
        ),
        alignment=AlignmentInputs(
            product_fit=1.0,
            workflow_fit=0.9,
            technical_feasibility=0.85,
            integration_feasibility=0.8,
            reuse_potential=0.9,
        ),
        risk=RiskInputs(
            liability=0.05,
            privacy=0.05,
            security=0.05,
            performance=0.25,
            dependency=0.15,
            implementation=0.2,
        ),
        confidence=ConfidenceInputs(
            data_quality=0.85,
            sample_size_score=0.75,
            model_confidence=0.7,
        ),
        static_urgency=0.85,
        fits_latency_budget=True,
    )


def candidate_from_pythia_brier(
    subject: str,
    *,
    sample_count: int,
    brier: float,
) -> SkillCandidate:
    return SkillCandidate(
        candidate_id=f"pythia-{subject[:32]}",
        skill_name=f"pythia_calibration:{subject}",
        problem_detected=f"Brier {brier:.3f} over {sample_count} samples",
        trigger_metric="brier",
        expected_lift=ExpectedLift(efficiency=0.7, satisfaction=0.5, scalability=0.6),
        alignment=AlignmentInputs(
            product_fit=0.9,
            workflow_fit=0.8,
            technical_feasibility=0.9,
            integration_feasibility=0.85,
            reuse_potential=0.8,
        ),
        risk=RiskInputs(performance=0.15, implementation=0.15, dependency=0.1),
        confidence=ConfidenceInputs(
            data_quality=0.8,
            sample_size_score=min(1.0, sample_count / 30.0),
            model_confidence=0.7,
        ),
        static_urgency=0.6,
        fits_latency_budget=True,
    )
