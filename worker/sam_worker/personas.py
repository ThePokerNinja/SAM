"""Persona definitions. Samuel is the host/face; the others are sub-agents he voices
by switching ElevenLabs voice_id during the Executive Brief (one agent, many voices)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Fallback Samuel prompt if the canon file is missing. Keeps the "never mention
# hermes" guardrail and the anti-hallucination core so the agent never ships
# without grounding rules. The full canon lives in prompts/samuel_canon.txt.
_SAMUEL_FALLBACK = (
    "You are Samuel ('Sam'), the single customer-facing Rainmaker agent. Warm, sharp, "
    "concise, confident. You host and cover trading/Rainmaker yourself. Never mention "
    "Hermes or 'Charles' - you are the only agent the user meets. Keep replies short "
    "and spoken. Never invent pricing, fees, an onboarding team, email/links, or account "
    "state; if you don't know, say so and offer a real next step."
)


def _load_samuel_canon() -> str:
    """Load the canon Samuel system prompt (SAM-004); fall back to the inline core."""
    path = Path(__file__).resolve().parent / "prompts" / "samuel_canon.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or _SAMUEL_FALLBACK
    except OSError:
        return _SAMUEL_FALLBACK


@dataclass(frozen=True)
class Persona:
    id: str
    display_name: str
    voice_env: str  # env var holding the ElevenLabs voice_id
    system_hint: str


SAMUEL = Persona(
    id="samuel",
    display_name="Samuel",
    voice_env="SAM_VOICE_ID",
    system_hint=_load_samuel_canon(),
)

SCHEDULE = Persona(
    id="schedule",
    display_name="Schedule Agent",
    voice_env="SCHEDULE_VOICE_ID",
    system_hint="You are the Schedule Agent: calendar, reminders, logistics. Crisp and upbeat.",
)

DESIGN = Persona(
    id="design",
    display_name="Design Agent",
    voice_env="DESIGN_VOICE_ID",
    system_hint="You are the Design Agent: UI/brand/creative. Playful, opinionated, visual.",
)

SALES = Persona(
    id="sales",
    display_name="Sales Agent",
    voice_env="SALES_VOICE_ID",
    system_hint="You are the Sales Agent: pipeline, outreach, conversions. Energetic closer.",
)

ALL: dict[str, Persona] = {p.id: p for p in (SAMUEL, SCHEDULE, DESIGN, SALES)}

# Demo personas other than the host (Samuel covers trading himself).
SUB_AGENTS = (SCHEDULE, DESIGN, SALES)
