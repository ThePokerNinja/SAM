"""SkillBuilder core data objects (skillbuilder-spec.md sec 5).

Pure dataclasses; no I/O. These are the source of truth for field names referenced by the spec.
Scoring lives in scoring.py; lifecycle in states.py; registry/graph in registry.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .states import CandidateStatus, DependencyType, SkillStatus


def _now() -> float:
    return time.time()


@dataclass
class Skill:
    """A deployed capability. Maps 1:1 to a runtime pack (ADR-13) once implemented."""

    skill_id: str
    name: str
    description: str = ""
    parent_skill_id: str | None = None
    version: str = "0.1.0"
    status: SkillStatus = SkillStatus.PROPOSED
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()


@dataclass
class KPISnapshot:
    """A metric over a period, with rolling stats for trend detection."""

    metric_name: str
    metric_value: float
    rolling_average: float = 0.0
    rolling_std_dev: float = 0.0
    period_start: str = ""
    period_end: str = ""


@dataclass
class ExpectedLift:
    """Inputs to the impact score (all 0..1 normalized expectations)."""

    revenue: float = 0.0
    retention: float = 0.0
    satisfaction: float = 0.0
    efficiency: float = 0.0
    scalability: float = 0.0


@dataclass
class AlignmentInputs:
    product_fit: float = 0.0
    workflow_fit: float = 0.0
    technical_feasibility: float = 0.0
    integration_feasibility: float = 0.0
    reuse_potential: float = 0.0


@dataclass
class RiskInputs:
    liability: float = 0.0
    privacy: float = 0.0
    security: float = 0.0
    performance: float = 0.0
    dependency: float = 0.0
    implementation: float = 0.0


@dataclass
class ConfidenceInputs:
    data_quality: float = 0.0
    sample_size_score: float = 0.0
    model_confidence: float = 0.0


@dataclass
class CandidateScores:
    impact_score: float = 0.0
    strategic_alignment_score: float = 0.0
    raw_risk_score: float = 0.0
    risk_adjusted_score: float = 0.0
    urgency_trend_score: float = 0.0
    confidence_score: float = 0.0
    skill_adoption_score: float = 0.0


@dataclass
class CandidateGates:
    meets_score_threshold: bool = False
    meets_alignment_threshold: bool = False
    meets_risk_threshold: bool = False
    meets_confidence_threshold: bool = False
    meets_latency_budget: bool = False
    approved_for_adoption: bool = False


@dataclass
class SkillCandidate:
    """A proposed skill under evaluation in the governance loop."""

    candidate_id: str
    skill_name: str
    problem_detected: str = ""
    trigger_metric: str = ""
    expected_lift: ExpectedLift = field(default_factory=ExpectedLift)
    alignment: AlignmentInputs = field(default_factory=AlignmentInputs)
    risk: RiskInputs = field(default_factory=RiskInputs)
    confidence: ConfidenceInputs = field(default_factory=ConfidenceInputs)
    static_urgency: float = 0.5
    # latency budget check: does the pack pre-warm fit ADR-8 (800ms)?
    fits_latency_budget: bool = True
    scores: CandidateScores = field(default_factory=CandidateScores)
    gates: CandidateGates = field(default_factory=CandidateGates)
    status: CandidateStatus = CandidateStatus.QUEUED
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)


@dataclass
class SkillExperiment:
    """An A/B record for an adopted skill."""

    experiment_id: str
    skill_id: str
    control_group_size: int = 0
    test_group_size: int = 0
    performance_delta: float = 0.0
    statistical_significance: float = 1.0  # p-value; significant when < 0.05
    winner: str = "control"  # control | test

    @property
    def is_significant(self) -> bool:
        return self.statistical_significance < 0.05


@dataclass
class SkillDependency:
    skill_id: str
    dependency_skill_id: str
    dependency_type: DependencyType = DependencyType.REQUIRED


@dataclass
class RetirementInputs:
    maintenance_cost: float = 0.0
    performance_decay: float = 0.0
    obsolescence_risk: float = 0.0
    replacement_availability: float = 0.0
