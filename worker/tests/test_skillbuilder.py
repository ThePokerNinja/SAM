"""Tests for the SkillBuilder scoring, gates, and registry (scaffold)."""

from __future__ import annotations

from sam_worker.skillbuilder.models import (
    AlignmentInputs,
    ConfidenceInputs,
    ExpectedLift,
    RetirementInputs,
    RiskInputs,
    SkillCandidate,
)
from sam_worker.skillbuilder.character_sheet import build_character_sheet
from sam_worker.skillbuilder.registry import default_registry
from sam_worker.skillbuilder.scoring import (
    confidence_score,
    evaluate_candidate,
    impact_score,
    raw_risk_score,
    retirement_score,
    should_retire,
    skill_adoption_score,
    strategic_alignment_score,
)
from sam_worker.skillbuilder.states import SkillStatus


def _full(value: float, cls):
    """Build an inputs dataclass with every field set to `value`."""
    import dataclasses

    return cls(**{f.name: value for f in dataclasses.fields(cls)})


def test_weighted_scores_sum_to_one_at_full() -> None:
    assert impact_score(_full(1.0, ExpectedLift)) == 1.0
    assert strategic_alignment_score(_full(1.0, AlignmentInputs)) == 1.0
    assert raw_risk_score(_full(1.0, RiskInputs)) == 1.0
    assert raw_risk_score(_full(0.0, RiskInputs)) == 0.0


def test_confidence_is_geometric_mean() -> None:
    c = ConfidenceInputs(data_quality=0.8, sample_size_score=0.8, model_confidence=0.8)
    assert abs(confidence_score(c) - 0.8) < 1e-9
    # A single zero collapses confidence to zero.
    assert confidence_score(ConfidenceInputs(0.0, 1.0, 1.0)) == 0.0


def test_adoption_weighting() -> None:
    assert skill_adoption_score(1.0, 1.0, 1.0, 1.0) == 1.0
    assert abs(skill_adoption_score(1.0, 0.0, 0.0, 0.0) - 0.50) < 1e-9


def test_strong_candidate_is_eligible() -> None:
    c = SkillCandidate(
        candidate_id="c1",
        skill_name="Adaptive Reminder",
        expected_lift=ExpectedLift(0.8, 0.8, 0.8, 0.8, 0.8),
        alignment=AlignmentInputs(0.9, 0.9, 0.9, 0.9, 0.9),
        risk=RiskInputs(0.1, 0.1, 0.1, 0.1, 0.1, 0.1),
        confidence=ConfidenceInputs(0.9, 0.9, 0.9),
        static_urgency=0.7,
        fits_latency_budget=True,
    )
    evaluate_candidate(c)
    assert c.scores.skill_adoption_score >= 0.80
    assert c.gates.approved_for_adoption is True


def test_high_risk_blocks_even_with_high_score() -> None:
    c = SkillCandidate(
        candidate_id="c2",
        skill_name="Risky Skill",
        expected_lift=ExpectedLift(1.0, 1.0, 1.0, 1.0, 1.0),
        alignment=AlignmentInputs(1.0, 1.0, 1.0, 1.0, 1.0),
        risk=RiskInputs(0.9, 0.9, 0.9, 0.9, 0.9, 0.9),  # raw risk ~0.9 > 0.40
        confidence=ConfidenceInputs(1.0, 1.0, 1.0),
        static_urgency=1.0,
        fits_latency_budget=True,
    )
    evaluate_candidate(c)
    assert c.gates.meets_risk_threshold is False
    assert c.gates.approved_for_adoption is False


def test_latency_budget_is_a_hard_gate() -> None:
    c = SkillCandidate(
        candidate_id="c3",
        skill_name="Heavy Skill",
        expected_lift=ExpectedLift(1.0, 1.0, 1.0, 1.0, 1.0),
        alignment=AlignmentInputs(1.0, 1.0, 1.0, 1.0, 1.0),
        risk=RiskInputs(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        confidence=ConfidenceInputs(1.0, 1.0, 1.0),
        static_urgency=1.0,
        fits_latency_budget=False,  # breaks ADR-8
    )
    evaluate_candidate(c)
    assert c.gates.meets_latency_budget is False
    assert c.gates.approved_for_adoption is False


def test_retirement_threshold() -> None:
    decayed = RetirementInputs(0.8, 0.8, 0.8, 0.8)
    assert retirement_score(decayed) == 0.8
    assert should_retire(decayed) is True
    assert should_retire(RetirementInputs(0.1, 0.1, 0.1, 0.1)) is False


def test_default_registry_dependency_gating() -> None:
    reg = default_registry()
    trading = reg.get("trading")
    assert trading is not None and trading.status == SkillStatus.IMPLEMENTED
    # Trading has no deps -> implementable. Appointment needs unimplemented deps -> blocked.
    assert reg.can_implement("trading") is True
    assert reg.can_implement("appointment") is False
    assert "calendar" in reg.required_dependencies("appointment")


def test_character_sheet_reflects_today() -> None:
    sheet = build_character_sheet()
    # Level == implemented skills; today only Trading is live.
    assert sheet["level"] == 1
    assert "Rainmaker Trading" in sheet["skills"]["mastered"]
    # The planned trio is honestly shown as not-yet-learned.
    not_learned = sheet["skills"]["not_learned"]
    assert "Appointment" in not_learned
    assert "Speed-to-Lead" in not_learned
    assert "Moderator" in not_learned
    # Attributes are 0..100 bars.
    for v in sheet["attributes"].values():
        assert 0 <= v <= 100


def test_character_sheet_uses_live_kpis() -> None:
    sheet = build_character_sheet(kpis={"v2v_p50_ms": 750.0, "hallucination_rate": 0.0})
    assert sheet["attributes"]["reflexes"] == 100   # under the 800ms KPI
    assert sheet["attributes"]["grounding"] == 100  # no hallucination
