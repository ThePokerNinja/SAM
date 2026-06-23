"""Samuel HERO character sheet -- derive RPG-style stats from the skill registry + KPIs.

Spec: rainMaker/docs/design/sam-hero-card-spec.md.

Pure + testable. Produces the canonical stats snapshot (dict / JSON) that the HERO card renders.
Because the card renderer lives in a *separate* process (rm_api, per ADR-9: SAM never shares code
with the Rainmaker monorepo), this module's JSON is the contract -- rm_api consumes an equivalent
snapshot, not this code directly.
"""

from __future__ import annotations

import json
import time

from .registry import SkillRegistry, default_registry
from .states import Mastery, SkillStatus

# Map a skill's lifecycle status -> the mastery bucket shown on the card.
_STATUS_TO_MASTERY = {
    SkillStatus.IMPLEMENTED: Mastery.MASTERED,      # refined below by KPI health
    SkillStatus.TESTING: Mastery.LEARNING,
    SkillStatus.APPROVED: Mastery.NOT_LEARNED,
    SkillStatus.UNDER_REVIEW: Mastery.NOT_LEARNED,
    SkillStatus.QUEUED: Mastery.NOT_LEARNED,
    SkillStatus.PROPOSED: Mastery.NOT_LEARNED,
    SkillStatus.DEFERRED: Mastery.NOT_LEARNED,
    SkillStatus.NEEDS_MORE_DATA: Mastery.NOT_LEARNED,
    SkillStatus.REJECTED: Mastery.NOT_LEARNED,
    SkillStatus.RETIRED: Mastery.RETIRED,
}


def _bar(value: float) -> int:
    """Clamp a 0..1 score to a 0..100 attribute bar."""
    return max(0, min(100, round(value * 100)))


def _latency_attr(v2v_p50_ms: float | None) -> int:
    """Reflexes: 100 at/under the 800ms KPI, 0 at/over 1500ms (ADR-8)."""
    if v2v_p50_ms is None:
        return 0
    if v2v_p50_ms <= 800:
        return 100
    if v2v_p50_ms >= 1500:
        return 0
    return _bar((1500 - v2v_p50_ms) / (1500 - 800))


def build_character_sheet(
    registry: SkillRegistry | None = None,
    kpis: dict | None = None,
) -> dict:
    """Return Samuel's stats snapshot.

    `kpis` (optional) carries live signal; absent values use honest placeholders reflecting the
    state assessment (p50 ~1091ms, grounding not yet proven, memory not yet live, advisory autonomy).
    """
    reg = registry or default_registry()
    kpis = kpis or {}

    implemented = reg.implemented()
    all_skills = reg.all_skills()

    buckets: dict[str, list[str]] = {
        Mastery.MASTERED.value: [],
        Mastery.LEARNING.value: [],
        Mastery.NOT_LEARNED.value: [],
        Mastery.RETIRED.value: [],
    }
    healthy_kpi = kpis.get("skill_health", {})  # skill_id -> bool
    for s in all_skills:
        mastery = _STATUS_TO_MASTERY.get(s.status, Mastery.NOT_LEARNED)
        # An implemented skill is only "mastered" if KPIs are healthy; else it's still "learning".
        if mastery == Mastery.MASTERED and healthy_kpi.get(s.skill_id, True) is False:
            mastery = Mastery.LEARNING
        buckets[mastery.value].append(s.name)

    breadth = len(implemented) / len(all_skills) if all_skills else 0.0

    autonomy_mode = kpis.get("autonomy_mode", "advisory")
    autonomy_attr = {"advisory": 25, "assisted": 60, "autonomous": 90}.get(autonomy_mode, 25)

    attributes = {
        "reflexes": _latency_attr(kpis.get("v2v_p50_ms", 1091.0)),
        "grounding": _bar(1.0 - kpis.get("hallucination_rate", 1.0)),
        "memory": _bar(kpis.get("memory_progress", 0.0)),
        "charm": _bar(kpis.get("charm", 0.7)),
        "skill_breadth": _bar(breadth),
        "autonomy": autonomy_attr,
    }

    return {
        "name": "SAMUEL",
        "title": "Systems Agent Model",
        "tagline": "One voice. Every skill.",
        "level": len(implemented),
        "attributes": attributes,
        "skills": buckets,
        "skill_counts": {k: len(v) for k, v in buckets.items()},
        "autonomy_mode": autonomy_mode,
        "as_of": time.strftime("%Y-%m-%d", time.gmtime()),
        "method_version": "0.1.0",
    }


def to_json(sheet: dict | None = None) -> str:
    return json.dumps(sheet or build_character_sheet(), indent=2, sort_keys=True)


if __name__ == "__main__":  # pragma: no cover
    print(to_json())
