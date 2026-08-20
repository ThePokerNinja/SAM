"""SAM-043: intake / briefing pipeline with provenance + consent flags."""

from __future__ import annotations

from dataclasses import dataclass, field


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
