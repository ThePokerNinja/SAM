"""Skill registry + skill-pack manifest skeleton (skillbuilder-spec.md sec 9; ADR-13).

Scaffold: an in-memory registry of Skills + dependency edges, plus the SkillPackManifest shape that
a runtime loader (Wave 6, SAM-039) will consume. No live loading here -- this is the catalog the
governance engine and the HERO character card read from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Skill, SkillDependency
from .states import DependencyType, SkillStatus


@dataclass
class SkillPackManifest:
    """ADR-13 pack shape. A Skill becomes runnable by attaching one of these.

    Loader (Wave 6) turns this into a live pack: persona overlay + tool subset + optional workflow
    + memory schema + safety rules + intake sources + artifacts, pre-warmed to respect ADR-8.
    """

    skill_id: str
    persona_overlay: str = ""             # appended to Samuel's system hint when active
    tools: list[str] = field(default_factory=list)        # tool names from the shared registry
    workflow: str | None = None           # optional workflow id
    memory_schema: dict | None = None     # pack-scoped memory shape
    safety_rules: list[str] = field(default_factory=list)
    intake_sources: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    prewarm: bool = True                  # pre-warm so activation costs no extra v2v turn


class SkillRegistry:
    """In-memory catalog of skills + dependency graph (scaffold)."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._manifests: dict[str, SkillPackManifest] = {}
        self._deps: list[SkillDependency] = []

    # --- registration -----------------------------------------------------
    def register(self, skill: Skill, manifest: SkillPackManifest | None = None) -> Skill:
        self._skills[skill.skill_id] = skill
        if manifest is not None:
            self._manifests[skill.skill_id] = manifest
        return skill

    def add_dependency(
        self, skill_id: str, dependency_skill_id: str, dep_type: DependencyType = DependencyType.REQUIRED
    ) -> None:
        self._deps.append(SkillDependency(skill_id, dependency_skill_id, dep_type))

    # --- queries ----------------------------------------------------------
    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def manifest(self, skill_id: str) -> SkillPackManifest | None:
        return self._manifests.get(skill_id)

    def dependencies(self, skill_id: str) -> list[SkillDependency]:
        return [d for d in self._deps if d.skill_id == skill_id]

    def required_dependencies(self, skill_id: str) -> list[str]:
        return [d.dependency_skill_id for d in self.dependencies(skill_id) if d.dependency_type == DependencyType.REQUIRED]

    def implemented(self) -> list[Skill]:
        return [s for s in self._skills.values() if s.status == SkillStatus.IMPLEMENTED]

    # --- gating -----------------------------------------------------------
    def can_implement(self, skill_id: str) -> bool:
        """A skill cannot be implemented until all REQUIRED dependencies are implemented."""
        for dep_id in self.required_dependencies(skill_id):
            dep = self._skills.get(dep_id)
            if dep is None or dep.status != SkillStatus.IMPLEMENTED:
                return False
        return True


def default_registry() -> SkillRegistry:
    """Seed registry with the trading base skill + the planned skill graph (statuses reflect today).

    Trading is the only IMPLEMENTED skill today (it is Samuel himself). Appointment / Speed-to-Lead
    / Moderator are PROPOSED with their dependency edges, so the character card shows them as
    'not yet learned' and the engine knows what to build toward.
    """
    reg = SkillRegistry()

    reg.register(
        Skill(skill_id="trading", name="Rainmaker Trading", status=SkillStatus.IMPLEMENTED,
              description="Samuel's native capability: grounded scans/pulse/trades (read-only first)."),
        SkillPackManifest(skill_id="trading", tools=["get_scans", "get_pulse", "get_trades"]),
    )

    # Sub-skills the bigger skills depend on (mostly not-yet-learned).
    for sid, name in [
        ("calendar", "Calendar"),
        ("reminder", "Reminder"),
        ("contact_resolution", "Contact Resolution"),
        ("attendance_prediction", "Attendance Prediction"),
        ("follow_up", "Follow-Up"),
        ("crm", "CRM Link"),
    ]:
        reg.register(Skill(skill_id=sid, name=name, status=SkillStatus.PROPOSED))

    reg.register(Skill(skill_id="appointment", name="Appointment", status=SkillStatus.PROPOSED,
                       description="Schedule/confirm/conduct/follow-up/rebook appointments."))
    reg.add_dependency("appointment", "calendar")
    reg.add_dependency("appointment", "reminder")
    reg.add_dependency("appointment", "contact_resolution")
    reg.add_dependency("appointment", "attendance_prediction", DependencyType.OPTIONAL)
    reg.add_dependency("appointment", "follow_up", DependencyType.OPTIONAL)

    reg.register(Skill(skill_id="speed_to_lead", name="Speed-to-Lead", status=SkillStatus.PROPOSED,
                       description="Missed-call follow-up + lead qualification + retention."))
    reg.add_dependency("speed_to_lead", "contact_resolution")
    reg.add_dependency("speed_to_lead", "crm")
    reg.add_dependency("speed_to_lead", "follow_up")

    reg.register(Skill(skill_id="moderator", name="Moderator", status=SkillStatus.PROPOSED,
                       description="Neutral consumer conflict-resolution (first non-trading pack)."))

    return reg
