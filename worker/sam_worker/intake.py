"""SAM-043: intake / briefing pipeline with provenance + consent flags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BriefItem:
    text: str
    provenance: str
    confidence: float = 0.5
    consent: bool = True


@dataclass
class SessionBrief:
    items: tuple[BriefItem, ...] = ()

    def as_prompt(self, *, token_budget: int = 400) -> str:
        lines = []
        used = 0
        for item in self.items:
            if not item.consent:
                continue
            line = f"- ({item.provenance}, {item.confidence:.2f}) {item.text}"
            used += len(line)
            if used > token_budget:
                break
            lines.append(line)
        return "\n".join(lines)


def assemble_brief(*sources: tuple[BriefItem, ...]) -> SessionBrief:
    items: list[BriefItem] = []
    for src in sources:
        items.extend(src)
    return SessionBrief(items=tuple(items))


def brief_from_artifacts(artifacts: list[Any]) -> SessionBrief:
    """Convert durable session outputs into provenance-labeled next-session context."""
    items: list[BriefItem] = []
    for artifact in artifacts:
        payload = getattr(artifact, "payload", {}) or {}
        text = str(payload.get("text") or "").strip()
        if not text and payload.get("items"):
            text = "; ".join(
                str(item.get("statement") or item.get("text") or "").strip()
                for item in payload["items"]
                if isinstance(item, dict)
            )
        if not text:
            continue
        items.append(
            BriefItem(
                text=text[:1000],
                provenance=f"artifact:{getattr(artifact, 'id', 'unknown')}",
                confidence=1.0,
                consent=True,
            )
        )
    return SessionBrief(items=tuple(items))
