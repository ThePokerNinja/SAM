"""Staging-only GPT-Live-1 talking front with client delegation (ADR-30 draft).

Production stays cascade (SAM_VOICE_ARCH=cascade). Enable with:
  SAM_VOICE_ARCH=gpt-live
  OPENAI_API_KEY=...
  Room prefix: staging-* or sam-gptlive-*

See rainMaker/studios/research/sam-human-conversation.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from livekit.agents import Agent, AgentSession, JobContext
from livekit.plugins.openai.realtime import GPTLiveDelegation, GPTLiveModel

from .config import Settings, effective_model_for_tier, resolve_brain
from .prompt_budget import samuel_instructions

_log = logging.getLogger("sam_worker.gpt_live_lab")

# Short live prompt — long canon + tools run on the delegated backend.
LIVE_INSTRUCTIONS = """You are Samuel ("Sam"), Michael's voice on Rainmaker. Warm, sharp, concise.
This is spoken conversation: one or two sentences, then listen.
Distinguish a backchannel ("yeah", "uh-huh") from a new question.
Keep the floor during the caller's thinking pause — do not fill silence.
Never mention Hermes or Charles. Delegate Rainmaker facts to the backend; do not invent numbers.
Participate in the conversation; do not read a FAQ brochure."""

_STAGING_PREFIXES = ("staging-", "sam-gptlive-")


def gpt_live_lab_enabled(settings: Settings, room_name: str) -> bool:
    """True when staging GPT-Live lab should replace the cascade for this room."""
    if (settings.voice_arch or "cascade").strip().lower() != "gpt-live":
        return False
    room = (room_name or "").strip().lower()
    if not any(room.startswith(prefix) for prefix in _STAGING_PREFIXES):
        _log.warning(
            "SAM_VOICE_ARCH=gpt-live ignored for room %r — requires staging-* or sam-gptlive-*",
            room_name,
        )
        return False
    if not (settings.openai_api_key or os.getenv("OPENAI_API_KEY", "").strip()):
        _log.error("SAM_VOICE_ARCH=gpt-live requires OPENAI_API_KEY")
        return False
    return True


def _resolve_voice(settings: Settings) -> str | dict[str, Any]:
    custom = (settings.openai_custom_voice_id or "").strip()
    if custom:
        return {"id": custom}
    stock = (settings.gpt_live_voice or "meridian").strip() or "meridian"
    return stock


def build_gpt_live_model(settings: Settings) -> GPTLiveModel:
    return GPTLiveModel(
        model=settings.gpt_live_model,
        voice=_resolve_voice(settings),
        delegation="client",
    )


async def _delegated_spoken_reply(settings: Settings, user_text: str) -> str:
    """One-shot backend: full Samuel canon + user turn → short spoken answer."""
    user_text = (user_text or "").strip()
    if not user_text:
        return "I'm here — go ahead."

    system = (
        samuel_instructions()
        + "\n\nReply in one or two short spoken sentences for the voice layer. "
        "No markdown, no lists, no IDs."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]

    brain = resolve_brain(settings)
    if brain == "groq" and settings.groq_api_key:
        url = f"{settings.groq_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
        model = settings.groq_model
    elif settings.openai_api_key:
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        model = effective_model_for_tier(2, settings)
    else:
        return "I'm having trouble reaching the backend right now."

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": min(settings.llm_max_completion_tokens, 180),
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
        content = body["choices"][0]["message"]["content"]
        spoken = str(content or "").strip()
        return spoken[:400] if spoken else "Got it."
    except Exception as exc:  # noqa: BLE001
        _log.exception("delegated backend failed: %s", exc)
        return "Give me a second — I'm still pulling that together."


def _register_delegation_handler(agent: Agent, settings: Settings) -> None:
    """Answer GPT-Live client delegations via Groq/OpenAI backend."""

    async def _handle(delegation: GPTLiveDelegation) -> None:
        try:
            duplex = agent.duplex_session
        except RuntimeError:
            _log.warning("delegation received before duplex session ready")
            return
        spoken = await _delegated_spoken_reply(settings, delegation.pending_transcript)
        duplex.append_commentary(spoken, delegation_id=delegation.id)
        _log.info(
            "gpt-live delegation answered id=%s chars=%d",
            delegation.id[:8],
            len(spoken),
        )

    def _on_delegation(delegation: GPTLiveDelegation) -> None:
        asyncio.ensure_future(_handle(delegation))

    duplex = agent.duplex_session
    duplex.on("delegation_created", _on_delegation)


async def run_gpt_live_entrypoint(
    ctx: JobContext,
    settings: Settings,
    *,
    room_name: str,
    is_phone: bool = False,
) -> None:
    """Minimal staging agent: GPT-Live talks; backend answers delegations."""
    if is_phone:
        _log.warning("gpt-live lab on phone room %s — portal/staging only recommended", room_name)

    voice = _resolve_voice(settings)
    model = build_gpt_live_model(settings)
    session = AgentSession(llm=model)
    agent = Agent(instructions=LIVE_INSTRUCTIONS)

    await session.start(agent=agent, room=ctx.room)
    await ctx.connect()

    _register_delegation_handler(agent, settings)

    git_sha = (os.getenv("RENDER_GIT_COMMIT") or "")[:12]
    _log.info(
        "GPT-Live lab active | room=%s | model=%s | voice=%s | git=%s",
        room_name,
        settings.gpt_live_model,
        voice if isinstance(voice, str) else json.dumps(voice),
        git_sha,
    )

    payload = {
        "type": "worker_info",
        "voice_arch": "gpt-live",
        "brain": "delegated",
        "gpt_live_model": settings.gpt_live_model,
        "gpt_live_voice": voice if isinstance(voice, str) else voice.get("id", ""),
        "room": room_name,
        "git": git_sha,
    }
    try:
        await ctx.room.local_participant.publish_data(
            json.dumps(payload).encode("utf-8"),
            topic="sam-bench",
            reliable=True,
        )
    except Exception:  # noqa: BLE001
        _log.debug("worker_info publish failed", exc_info=True)

    await session.generate_reply(
        instructions="Greet Michael warmly in one short spoken sentence, then listen."
    )
