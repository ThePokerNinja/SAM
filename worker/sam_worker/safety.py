"""SAM-045 trimmed: consent, recording defaults off, graceful pause/exit.

Crisis detection and human escalation were cut by operator decision 2026-08-20
(ADR-19 amendment). Recording defaults off (California all-party consent).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .session import Session


@dataclass
class ConsentRecord:
    participant_id: str
    recording: bool = False
    memory: bool = False
    spoken_confirmation: bool = False


@dataclass
class SafetyState:
    consents: dict[str, ConsentRecord] = field(default_factory=dict)

    def confirm_spoken(self, participant_id: str) -> None:
        rec = self.consents.setdefault(participant_id, ConsentRecord(participant_id))
        rec.spoken_confirmation = True

    def recording_allowed(self) -> bool:
        if not self.consents:
            return False
        return all(c.recording and c.spoken_confirmation for c in self.consents.values())

    def request_pause(self, session: Session) -> str:
        session.pause()
        return "Let's pause. Either of you can pick this back up whenever you're ready."

    def request_exit(self, session: Session) -> str:
        session.pause()
        return "We can stop here. I'll keep the understanding map from this session."
