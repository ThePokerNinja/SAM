"""Skill / candidate lifecycle states (skillbuilder-spec.md sec 8).

Plain string enums so they serialize cleanly to JSON / SMS / the character card.
"""

from __future__ import annotations

from enum import Enum


class SkillStatus(str, Enum):
    """Status of a deployed Skill (maps to a runtime pack once implemented)."""

    PROPOSED = "proposed"
    QUEUED = "queued"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"            # passed gates; awaiting owner consent
    TESTING = "testing"             # in A/B
    IMPLEMENTED = "implemented"     # live
    DEFERRED = "deferred"
    NEEDS_MORE_DATA = "needs_more_data"
    REJECTED = "rejected"
    RETIRED = "retired"


class CandidateStatus(str, Enum):
    """Status of a SkillCandidate moving through the governance loop."""

    PROPOSED = "proposed"
    QUEUED = "queued"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    NEEDS_MORE_DATA = "needs_more_data"
    IMPLEMENTED = "implemented"
    RETIRED = "retired"


class DependencyType(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


# Mastery buckets the character card (HERO) renders from registry + KPI signal.
class Mastery(str, Enum):
    MASTERED = "mastered"          # implemented + KPIs healthy
    LEARNING = "learning"         # implemented/testing, KPIs improving or not yet proven
    NOT_LEARNED = "not_learned"   # proposed/queued/approved, not yet live
    RETIRED = "retired"
