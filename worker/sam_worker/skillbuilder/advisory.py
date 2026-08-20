"""SAM-057: SkillBuilder advisory loop. Never auto-adopts."""

from __future__ import annotations

from .models import SkillCandidate
from .runtime import SkillBuilderRuntime
from .scoring import evaluate_candidate
from .states import CandidateStatus


def run_advisory(
    runtime: SkillBuilderRuntime,
    candidate: SkillCandidate,
    *,
    reason: str,
    trust_tier: str = "T1",
) -> SkillCandidate:
    """detect gap -> score -> APPROVAL_NEEDED. Owner consent is the only promotion path."""
    evaluate_candidate(candidate)
    runtime.request_approval(
        candidate.candidate_id,
        reason=reason,
        trust_tier=trust_tier,
    )
    candidate.status = CandidateStatus.UNDER_REVIEW
    return candidate
