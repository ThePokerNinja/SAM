"""Moderator v0: agreement spectrum + understanding map. No crisis layer."""

from __future__ import annotations

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


NEUTRALITY_FORBIDDEN = (
    "you're wrong",
    "that's your fault",
    "you should leave",
    "they're the problem",
)


def is_neutral(reply: str) -> bool:
    t = (reply or "").lower()
    return not any(p in t for p in NEUTRALITY_FORBIDDEN)
