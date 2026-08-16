"""SkillBuilder -- Samuel's skill governance engine.

The #2 flagship: discovers, scores, gates, deploys, measures, evolves, and retires Samuel's skills.
Spec: rainMaker/docs/design/skillbuilder-spec.md.

The runtime persists KPI evidence and defaults adoption to denied until explicit owner-consent
evidence is recorded.
"""

from .character_sheet import build_character_sheet, to_json
from .models import (
    KPISnapshot,
    Skill,
    SkillCandidate,
    SkillDependency,
    SkillExperiment,
)
from .registry import SkillPackManifest, SkillRegistry, default_registry
from .runtime import SkillBuilderRuntime
from .scoring import evaluate_candidate, retirement_score, should_retire
from .states import CandidateStatus, Mastery, SkillStatus

__all__ = [
    "Skill",
    "SkillCandidate",
    "SkillExperiment",
    "SkillDependency",
    "KPISnapshot",
    "SkillRegistry",
    "SkillPackManifest",
    "SkillBuilderRuntime",
    "default_registry",
    "evaluate_candidate",
    "retirement_score",
    "should_retire",
    "build_character_sheet",
    "to_json",
    "SkillStatus",
    "CandidateStatus",
    "Mastery",
]
