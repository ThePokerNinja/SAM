"""SkillBuilder scoring + gates (skillbuilder-spec.md sec 6-7, 8).

Deterministic, pure functions. Unit-tested against the worked examples in the source framework
(SAM/skills/agent_skill_builder_governance_framework.md).

Weights: Impact 50% / Alignment 25% / Risk 15% / Urgency 10%.
Gates: adoption>=0.80, alignment>=0.70, raw_risk<=0.40, confidence>=0.60, latency budget OK.
"""

from __future__ import annotations

from .models import (
    AlignmentInputs,
    CandidateGates,
    CandidateScores,
    ConfidenceInputs,
    ExpectedLift,
    RetirementInputs,
    RiskInputs,
    SkillCandidate,
)

# Gate thresholds (single source of truth).
ADOPTION_MIN = 0.80
ALIGNMENT_MIN = 0.70
RISK_MAX = 0.40
CONFIDENCE_MIN = 0.60
RETIREMENT_THRESHOLD = 0.75


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def impact_score(lift: ExpectedLift) -> float:
    return (
        lift.revenue * 0.30
        + lift.retention * 0.20
        + lift.satisfaction * 0.20
        + lift.efficiency * 0.15
        + lift.scalability * 0.15
    )


def strategic_alignment_score(a: AlignmentInputs) -> float:
    return (
        a.product_fit * 0.30
        + a.workflow_fit * 0.25
        + a.technical_feasibility * 0.20
        + a.integration_feasibility * 0.15
        + a.reuse_potential * 0.10
    )


def raw_risk_score(r: RiskInputs) -> float:
    return (
        r.liability * 0.25
        + r.privacy * 0.20
        + r.security * 0.15
        + r.performance * 0.15
        + r.dependency * 0.10
        + r.implementation * 0.15
    )


def risk_adjusted_score(r: RiskInputs) -> float:
    return 1.0 - raw_risk_score(r)


def confidence_score(c: ConfidenceInputs) -> float:
    """Geometric mean of data quality, sample-size score, model confidence."""
    product = max(0.0, c.data_quality) * max(0.0, c.sample_size_score) * max(0.0, c.model_confidence)
    return product ** (1.0 / 3.0)


def trend_score(current: float, rolling_avg: float, rolling_std: float) -> float:
    if rolling_std <= 0:
        return 0.0
    return (current - rolling_avg) / rolling_std


def urgency_trend_score(
    current_urgency: float,
    rolling_avg_urgency: float,
    rolling_std_urgency: float,
    *,
    static_fallback: float = 0.5,
) -> float:
    if rolling_std_urgency <= 0:
        return _clamp01(static_fallback)
    raw = 0.5 + ((current_urgency - rolling_avg_urgency) / rolling_std_urgency) * 0.1
    return _clamp01(raw)


def skill_adoption_score(
    impact: float, alignment: float, risk_adjusted: float, urgency: float
) -> float:
    return impact * 0.50 + alignment * 0.25 + risk_adjusted * 0.15 + urgency * 0.10


def lift(test_performance: float, control_performance: float) -> float:
    if control_performance == 0:
        return 0.0
    return (test_performance - control_performance) / control_performance


def retirement_score(r: RetirementInputs) -> float:
    return (
        r.maintenance_cost * 0.30
        + r.performance_decay * 0.30
        + r.obsolescence_risk * 0.20
        + r.replacement_availability * 0.20
    )


def should_retire(r: RetirementInputs) -> bool:
    return retirement_score(r) > RETIREMENT_THRESHOLD


def evaluate_candidate(candidate: SkillCandidate) -> SkillCandidate:
    """Compute all scores + gates for a candidate, mutating and returning it.

    Note: passing gates makes a candidate ELIGIBLE for adoption. The actual promotion to
    `implemented` is an owner-consent action routed through Hermes/studios (skillbuilder-spec sec 3);
    `approved_for_adoption=True` only means "the math says yes, now ask the human".
    """
    impact = impact_score(candidate.expected_lift)
    alignment = strategic_alignment_score(candidate.alignment)
    raw_risk = raw_risk_score(candidate.risk)
    risk_adj = 1.0 - raw_risk
    confidence = confidence_score(candidate.confidence)
    urgency = _clamp01(candidate.static_urgency)
    adoption = skill_adoption_score(impact, alignment, risk_adj, urgency)

    candidate.scores = CandidateScores(
        impact_score=round(impact, 4),
        strategic_alignment_score=round(alignment, 4),
        raw_risk_score=round(raw_risk, 4),
        risk_adjusted_score=round(risk_adj, 4),
        urgency_trend_score=round(urgency, 4),
        confidence_score=round(confidence, 4),
        skill_adoption_score=round(adoption, 4),
    )

    g = CandidateGates(
        meets_score_threshold=adoption >= ADOPTION_MIN,
        meets_alignment_threshold=alignment >= ALIGNMENT_MIN,
        meets_risk_threshold=raw_risk <= RISK_MAX,
        meets_confidence_threshold=confidence >= CONFIDENCE_MIN,
        meets_latency_budget=bool(candidate.fits_latency_budget),
    )
    g.approved_for_adoption = (
        g.meets_score_threshold
        and g.meets_alignment_threshold
        and g.meets_risk_threshold
        and g.meets_confidence_threshold
        and g.meets_latency_budget
    )
    candidate.gates = g
    return candidate
