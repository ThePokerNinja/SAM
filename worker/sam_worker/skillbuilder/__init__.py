"""SkillBuilder -- Samuel's skill governance engine (scaffold).

The #2 flagship: discovers, scores, gates, deploys, measures, evolves, and retires Samuel's skills.
Spec: rainMaker/docs/design/skillbuilder-spec.md.

Scaffold scope: the data model, the deterministic scoring/gates, the registry + pack-manifest shape,
the lifecycle states, and the character sheet (HERO stats) are real and testable. Live wiring to
the runtime (packs, KPIs, A/B, Hermes consent) lands after Wave 1 + Wave 6.
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
