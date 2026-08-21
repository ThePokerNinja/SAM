"""Moderator v0: agreement spectrum + understanding map. No crisis layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Band = Literal["agree", "unlikely", "cant", "wont", "absolutely_wont"]

BANDS: tuple[Band, ...] = ("agree", "unlikely", "cant", "wont", "absolutely_wont")


def classify(text: str) -> Band:
    t = (text or "").lower()
    if any(w in t for w in ("never", "absolutely not", "deal breaker")):
        return "absolutely_wont"
    if any(w in t for w in ("won't", "will not", "refuse")):
        return "wont"
    if any(w in t for w in ("can't", "cannot", "unable")):
        return "cant"
    if any(w in t for w in ("maybe", "not sure", "unlikely")):
        return "unlikely"
    if any(w in t for w in ("agree", "yes", "same page")):
        return "agree"
    return "unlikely"


def understanding_map(topics: list[tuple[str, str]]) -> dict:
    rows = [{"topic": topic, "band": classify(utterance)} for topic, utterance in topics]
    return {"kind": "understanding_map", "topics": rows}


@dataclass
class ModeratorRuntime:
    """Session-local agreement tracking; durable output is emitted at close."""

    statements: dict[str, list[str]] = field(default_factory=dict)

    def observe(self, speaker_id: str, text: str) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        self.statements.setdefault(speaker_id or "unknown", []).append(clean[:800])

    def has_content(self) -> bool:
        return any(self.statements.values())

    def understanding_artifact(self) -> dict:
        topics: list[dict[str, str]] = []
        for speaker_id, statements in self.statements.items():
            for index, statement in enumerate(statements, start=1):
                topics.append(
                    {
                        "topic": f"{speaker_id}:{index}",
                        "speaker_id": speaker_id,
                        "statement": statement,
                        "band": classify(statement),
                    }
                )
        return {"kind": "understanding_map", "topics": topics}

    def next_steps_artifact(self) -> dict:
        unresolved = [
            row
            for row in self.understanding_artifact()["topics"]
            if row["band"] != "agree"
        ]
        return {
            "kind": "next_steps",
            "items": [
                {
                    "speaker_id": row["speaker_id"],
                    "statement": row["statement"],
                    "status": row["band"],
                }
                for row in unresolved[-8:]
            ],
        }


NEUTRALITY_FORBIDDEN = (
    "you're wrong",
    "that's your fault",
    "you should leave",
    "they're the problem",
)


def is_neutral(reply: str) -> bool:
    t = (reply or "").lower()
    return not any(p in t for p in NEUTRALITY_FORBIDDEN)
