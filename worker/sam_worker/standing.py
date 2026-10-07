"""Standing callbacks the owner states in plain speech, plus the last-call hook."""

from __future__ import annotations

import re

_WHEN_I_SAY = re.compile(
    r"(?:when|every time) i say\s+(?P<trigger>.+?)\s*,?\s*"
    r"(?:that you respond and say|you respond and say|you say|say)\s+(?P<reply>.+)",
    re.IGNORECASE,
)
_REMEMBER_THAT = re.compile(r"\bremember that\s+(?P<body>.+)", re.IGNORECASE)


def parse_standing_instruction(text: str) -> str | None:
    """Turn 'when I say X, say Y' into a line injected on the next turn."""
    raw = " ".join((text or "").split())
    if not raw:
        return None
    match = _WHEN_I_SAY.search(raw)
    if match:
        trigger = match.group("trigger").strip(" .,")
        reply = match.group("reply").strip(" .,")
        trigger = re.sub(r"^(that|sam)\s+", "", trigger, flags=re.IGNORECASE).strip()
        if trigger and reply:
            return f'When the owner says "{trigger}", respond: {reply}.'
    remembered = _REMEMBER_THAT.search(raw)
    if remembered:
        body = remembered.group("body").strip(" .,")
        if len(body) >= 8:
            return body
    return None


def standing_turn_note(lines: list[str]) -> str:
    kept = [line.strip() for line in lines if line and line.strip()]
    if not kept:
        return ""
    return (
        "Standing instructions the owner already set. Follow them when they say "
        "the trigger. Do not ask them to repeat the instruction:\n"
        + "\n".join(f"- {line}" for line in kept)
    )


def prior_topic_hook(summary: str) -> str:
    """One concrete hook from the last thread, for the opening sentence."""
    text = (summary or "").strip()
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("room=") or stripped.startswith("engagement="):
            continue
        if stripped.lower().startswith("open loops:"):
            continue
        lines.append(stripped)
    blob = " ".join(lines)
    blob = re.sub(r"^Opening:\s*", "", blob, flags=re.IGNORECASE)
    piece = blob.split("|")[0].strip()
    piece = re.sub(r"^Topic:\s*", "", piece, flags=re.IGNORECASE)
    return piece[:140].rstrip(" .")
