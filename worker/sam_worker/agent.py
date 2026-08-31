"""Real LiveKit agent (Phase 5b) - Samuel, with per-turn voice-to-voice latency logging.

Pipeline (ADR-1/3/4/5):
  STT : LiveKit Inference by default; Deepgram direct when DEEPGRAM_API_KEY is set (SAM_STT=deepgram).
  LLM : OpenAI-compatible client pointed at Groq (live tier, openai/gpt-oss-20b).
  TTS : ElevenLabs Flash v2.5 streaming (our key), Samuel's voice.
  VAD : Silero (prewarmed). Preemptive generation on.

Run (needs worker/.env with LIVEKIT_*, GROQ_API_KEY or OPENAI_API_KEY, ELEVENLABS_API_KEY, SAM_VOICE_ID):
  python -m sam_worker.agent console   # local mic/speaker, fastest way to hear Sam + read v2v
  python -m sam_worker.agent dev       # register a worker with LiveKit Cloud; join via Agents Playground

Per turn it logs: EOU delay + LLM TTFT + TTS TTFB = v2v, flagged against the 800ms KPI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

# Windows consoles default to cp1252; LiveKit's CLI banner prints an emoji that crashes
# the charmap codec. Force UTF-8 on our streams before any livekit import prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    WorkerOptions,
    cli,
    function_tool,
    llm,
    metrics,
)
from livekit.plugins import (  # noqa: F401 — register on main thread
    deepgram,
    elevenlabs,
    openai,
    silero,
)

from .alerts import GROQ_429, BurstTracker
from .artifacts import Artifact, ArtifactStore
from .config import Settings, resolve_brain
from .context import assemble_context
from .health import start_health_server
from .nightly import start_nightly_scheduler
from .intake import brief_from_artifacts
from .latency import TurnProfile, latency_log_enabled, write_profile
from .memory import (
    Episode,
    EpisodicMemoryStore,
    MemoryRetriever,
    ProfileFact,
    ProfileStore,
    extract_explicit_profile_update,
)
from .outbound import (
    decode_outbound_metadata,
    is_outbound_dial_room,
    pick_outbound_metadata,
    take_pending_script,
    wait_for_outbound_answer,
)
from .owner_gate import (
    build_owner_gate,
    sip_caller_is_authorized,
    wire_owner_gate_listeners,
)
from .packs.moderator import ModeratorRuntime
from .prompt_budget import samuel_instructions
from .pythia import BaselineStore, ForecastLedger, predict_threshold_event
from .router import FastIntentRouter, RoutedSamuelAgent
from .continuity import (
    ContinuityState,
    brief_from_thread_summary,
    build_thread_summary_text,
    effective_history_token_cap,
    engagement_fields_for_context,
    extract_open_loops,
    owner_memory_token_cap,
)
from .demo_cap import GOODBYE, TURN_MINUTES, TURN_TOKENS, is_capped_room, should_hangup
from .session import (
    BUILDER_OPENING,
    BUILDER_REASK,
    allows_skill_approval_sms,
    build_session,
    greeting_instructions,
    should_speak_builder_opening,
)
from .session_log import SessionLogger
from .safety import SafetyState
from .skillbuilder.advisory import run_advisory
from .skillbuilder.gap import candidate_from_latency, candidate_from_pythia_brier
from .skillbuilder.models import KPISnapshot
from .skillbuilder.runtime import SkillBuilderRuntime
from .skillbuilder.snapshot import live_snapshot, write_snapshot
from .surfaces import surface_for
from .stt import build_stt
from .packs import PackRegistry
from .tier import TierState
from .tier_session import apply_tier_to_session, parse_tier_payload
from .tool_latency import ToolLatencyManager
from .tools.handlers import build_rainmaker_client, handle_commit_calendar_change, handle_named_tool
from .tools.rainmaker_registry import engagement_id_from_room, register_rainmaker_tools
from .tools.registry import ToolRegistry
from .turns import build_turn_handling
from .voice_verify import VoiceVerifier

# Spoken refusal when a Tier-T (trigger) tool is called by a non-owner session.
_OWNER_ONLY = (
    "I can only do that for the owner, and I didn't recognize your voice just now. "
    "I can still read you the scans, the pulse, trades, or research."
)

TIER_TOPIC = "sam-tier"
CHAT_TOPIC = "sam-chat"


def _conversation_item_text(item: object) -> str:
    text = getattr(item, "text_content", None)
    if text:
        return str(text).strip()
    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            else:
                parts.append(str(getattr(part, "text", "") or getattr(part, "content", "") or ""))
        return " ".join(part for part in parts if part).strip()
    return ""


def first_builder_dump_id(room_name: str, text: str, *, already: bool) -> str:
    """First non-SYNC user turn in a builder- room is the job dump."""
    if already or not should_speak_builder_opening(room_name):
        return ""
    cleaned = (text or "").strip()
    if not cleaned or cleaned.startswith("[SYNC]"):
        return ""
    return engagement_id_from_room(room_name)


async def _run_scan_bg(client) -> None:
    """Fire the ~60s scan without blocking the voice turn; results land in /scan/latest."""
    try:
        res = await client.run_scan()
        if not res.get("ok"):
            _log.warning("background scan run failed: %s", res.get("error"))
    except Exception:  # noqa: BLE001
        _log.exception("background scan run crashed")


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    return registry


async def _wait_for_sip_participants(room, *, timeout_s: float = 12.0):
    """SIP callers join slightly after the agent connects; gating too early rejects everyone."""
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        participants = list(room.remote_participants.values())
        if participants:
            return participants
        await asyncio.sleep(0.1)
    return list(room.remote_participants.values())


load_dotenv()
_log = logging.getLogger("sam.agent")


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["phone_vad"] = silero.VAD.load(
        sample_rate=8000,
        min_silence_duration=0.35,
        prefix_padding_duration=0.3,
    )


def _build_llm(s: Settings):
    if resolve_brain(s) != "groq":
        return openai.LLM(
            model=s.openai_model,
            base_url=s.openai_base_url,
            api_key=s.openai_api_key,
            max_completion_tokens=s.llm_max_completion_tokens,
        )
    models = [s.groq_model]
    groq_fallback = s.groq_fallback_model or "openai/gpt-oss-120b"
    if groq_fallback not in models:
        models.append(groq_fallback)
    rungs = [
        openai.LLM(
            model=model,
            base_url=s.groq_base_url,
            api_key=s.groq_api_key,
            max_completion_tokens=s.llm_max_completion_tokens,
        )
        for model in models
    ]
    if s.openai_api_key:
        rungs.append(
            openai.LLM(
                model=s.openai_model,
                base_url=s.openai_base_url,
                api_key=s.openai_api_key,
                max_completion_tokens=s.llm_max_completion_tokens,
            )
        )
    if len(rungs) == 1:
        return rungs[0]
    return llm.FallbackAdapter(
        llm=rungs,
        attempt_timeout=2.5,
        max_retry_per_llm=2,
    )


def _error_status(error: Any) -> int | None:
    """Extract an HTTP status from LiveKit's nested error event safely."""
    seen: set[int] = set()
    current = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if isinstance(status, int) and status > 0:
            return status
        body = getattr(current, "body", None)
        if isinstance(body, dict):
            nested = body.get("error")
            code = body.get("code")
            if isinstance(nested, dict):
                code = code or nested.get("code")
            elif isinstance(nested, str):
                code = code or nested
            if "rate_limit" in str(code or "").lower():
                return 429
        current = (
            getattr(current, "error", None)
            or getattr(current, "__cause__", None)
            or getattr(current, "exception", None)
        )
    text = str(error or "").lower()
    if "429" in text or "rate_limit" in text or "tokens per minute" in text:
        return 429
    return None


def _is_missing_tool_error(error: Any) -> bool:
    text = str(error or "").lower()
    return "not in request.tools" in text or "tool call validation failed" in text


def _recovery_utterance(error: Any) -> str | None:
    if _is_missing_tool_error(error):
        return None
    if _error_status(error) == 429:
        return "Give me one moment."
    return "One sec."


def _event_time_ms(event: Any) -> float:
    created_at = getattr(event, "created_at", None)
    if isinstance(created_at, (int, float)) and created_at > 0:
        return float(created_at) * 1000.0
    return time.time() * 1000.0


def _start_barge_overlap(
    state: dict[str, float | None],
    event: Any,
    *,
    other_state: str | None,
) -> None:
    if (
        getattr(event, "new_state", None) == "speaking"
        and other_state == "speaking"
        and state.get("t0_ms") is None
    ):
        state["t0_ms"] = _event_time_ms(event)


def _finish_barge_overlap(
    state: dict[str, float | None],
    event: Any,
) -> float | None:
    if (
        getattr(event, "old_state", None) != "speaking"
        or getattr(event, "new_state", None) == "speaking"
        or state.get("t0_ms") is None
    ):
        return None
    measured = max(0.0, _event_time_ms(event) - float(state["t0_ms"]))
    state["t0_ms"] = None
    state["measured_ms"] = measured
    return measured


def _session_close_summary(turns: list[tuple[str, str]], *, limit: int = 6) -> str:
    recent = turns[-max(1, limit) :]
    return " | ".join(f"{role}: {text[:240]}" for role, text in recent)


def _session_decisions(turns: list[tuple[str, str]]) -> tuple[str, ...]:
    markers = ("we decided", "we agreed", "let's ", "i will ", "we will ")
    decisions = [
        text[:320]
        for role, text in turns
        if role == "user" and any(marker in text.lower() for marker in markers)
    ]
    return tuple(decisions[-8:])


async def entrypoint(ctx: JobContext) -> None:
    # Dedicated full-audio mode experiments run an in-process agent in these rooms.
    # The production worker must not create a second Samuel participant there.
    if (ctx.room.name or "").startswith("sam-wave8-embedded-"):
        _log.info("Skipping embedded benchmark room dispatch")
        return
    job_room = str(getattr(getattr(getattr(ctx, "job", None), "room", None), "name", "") or "")
    room_name = (ctx.room.name or job_room or "").strip()
    outbound_meta = decode_outbound_metadata(getattr(ctx.room, "metadata", "") or "")
    is_outbound_guest = is_outbound_dial_room(room_name) or outbound_meta["kind"] == "outbound_guest"
    outbound_script = {"spoken": str(outbound_meta.get("spoken") or "").strip(), "delivered": False}
    surface = (
        "phone"
        if room_name.startswith("call-") or is_outbound_guest
        else "portal"
    )
    surface_profile = surface_for(surface)
    is_phone = surface_profile.name == "phone"
    s = Settings.from_env()
    if is_phone:
        s = replace(s, stt_model=s.phone_stt_model)
    resolved = resolve_brain(s)
    brain = (resolved + ":" + (s.groq_model if resolved == "groq" else s.openai_model))
    stt = build_stt(s)
    stt_label = s.stt_model if not s.deepgram_api_key else f"deepgram/{s.stt_model.removeprefix('deepgram/')}"
    groq_fallback = (s.groq_fallback_model or "openai/gpt-oss-120b") if resolved == "groq" else "-"
    _log.info(
        "Samuel starting | brain=%s | groq_fallback=%s | openai_rung=%s | stt=%s | tts=%s streaming=livekit-elevenlabs-ws | turn=%s | endpoint=%.2f/%.2f | voice=%s",
        brain,
        groq_fallback,
        bool(s.openai_api_key) if resolved == "groq" else False,
        stt_label,
        s.elevenlabs_model,
        s.turn_mode,
        s.endpoint_min,
        s.endpoint_max,
        s.voice_ids["samuel"][:6],
    )

    session = AgentSession(
        stt=stt,
        llm=_build_llm(s),
        tts=elevenlabs.TTS(
            model=s.elevenlabs_model,
            voice_id=s.voice_ids["samuel"],
            api_key=s.elevenlabs_api_key,
        ),
        vad=ctx.proc.userdata["phone_vad" if is_phone else "vad"],
        turn_handling=build_turn_handling(s),
    )
    recovery_state: dict[str, Any] = {"task": None, "last_at": 0.0}
    groq_429_burst = BurstTracker(window_s=600.0, threshold=3)
    rm_holder: dict[str, Any] = {"client": None}

    async def _speak_recovery(error: Any) -> None:
        # LiveKit retries a failed LLM turn about every 2s. Speak recovery once
        # per burst so Groq 429s do not loop a recovery line.
        now = time.monotonic()
        if groq_429_burst.observe(now, is_match=_error_status(error) == 429):
            client = rm_holder.get("client")
            if client is not None:
                asyncio.ensure_future(
                    client.post_sam_alert(
                        GROQ_429,
                        detail="tokens-per-minute burst",
                        count=groq_429_burst.count,
                    )
                )
        if recovery_state["task"] is not None or now - recovery_state["last_at"] < 20.0:
            return
        spoken = _recovery_utterance(error)
        if not spoken:
            return
        recovery_state["last_at"] = now
        recovery_state["task"] = asyncio.current_task()
        try:
            await session.say(
                spoken,
                allow_interruptions=False,
                add_to_chat_ctx=False,
            )
        except Exception:  # noqa: BLE001
            _log.exception("session recovery speech failed")
        finally:
            recovery_state["task"] = None

    try:
        @session.on("error")
        def _on_session_error(ev) -> None:
            error = getattr(ev, "error", ev)
            _log.warning(
                "SESSION_ERROR kind=%s status=%s detail=%s",
                type(error).__name__,
                _error_status(error),
                str(error)[:300],
            )
            if recovery_state["task"] is None:
                asyncio.ensure_future(_speak_recovery(error))
    except Exception:  # noqa: BLE001
        _log.debug("session error recovery hook unavailable", exc_info=True)

    session_id = ctx.room.name or ctx.job.id
    pack_registry = PackRegistry()
    sam_session = build_session(session_id=session_id, surface=surface, room_name=room_name)
    safety_state = SafetyState()
    moderator_runtime = ModeratorRuntime()
    pack = pack_registry.activate(sam_session.pack)
    _log.info(
        "Session kind=%s pack=%s surface=%s",
        sam_session.kind,
        pack.id,
        sam_session.surface,
    )

    @ctx.room.on("participant_connected")
    def _track_session_participant(participant) -> None:
        participant_id = str(getattr(participant, "identity", "") or "").strip()
        if not participant_id:
            return
        display_name = str(getattr(participant, "name", "") or "").strip() or None
        if sam_session.participants[0].id == "host":
            sam_session.bind_host(participant_id, display_name)
            role = "host"
        else:
            sam_session.add_party(participant_id, display_name)
            role = next(
                item.role for item in sam_session.participants if item.id == participant_id
            )
        safety_state.register(participant_id)
        _log.info("SESSION_PARTICIPANT role=%s id=%s", role, participant_id)

    bench_events_enabled = session_id.startswith(("sam-wave8-", "call-", "staging-"))

    async def _publish_bench_event(payload: dict) -> None:
        if not bench_events_enabled:
            return
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(payload),
                reliable=True,
                topic="sam-bench",
            )
        except Exception:  # noqa: BLE001 - benchmark telemetry never affects speech
            _log.debug("benchmark event publish failed", exc_info=True)

    # Per-turn latency profiles (PDF Phase 1 / ADR-24). The headline v2v log line below is
    # unchanged; TurnProfile records the full per-stage breakdown and, when SAM_LATENCY_LOG=1,
    # appends a JSONL row for offline tier analysis (see bench/latency_profile.py).
    turns: dict[str, TurnProfile] = {}
    turn_counter = {"n": 0}
    last_transcript_chars: dict[str, int | None] = {"value": None}
    perf_state: dict[str, float | str | None] = {
        "route_ms": None,
        "route": None,
        "context_ms": None,
        "tool_ms": None,
    }
    # Barge-in is measured from overlapping user speech until playback leaves the
    # speaking state. It is attached to the next completed profile; absent events
    # remain None rather than fabricating a zero.
    barge_state = {"t0_ms": None, "measured_ms": None}  # type: dict[str, float | None]

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        m = ev.metrics
        sid = getattr(m, "speech_id", None)
        if not sid:
            return
        t = turns.setdefault(sid, TurnProfile(speech_id=sid, turn_mode=s.turn_mode))
        if isinstance(m, metrics.EOUMetrics):
            turn_counter["n"] += 1
            t.eou_ms = m.end_of_utterance_delay * 1000
            t.turn_index = turn_counter["n"]
            t.transcript_chars = last_transcript_chars["value"]
            td = getattr(m, "transcription_delay", None)
            if td is not None:
                t.transcription_delay_ms = td * 1000
            callback = getattr(m, "on_user_turn_completed_delay", None)
            if callback is not None:
                t.turn_callback_ms = callback * 1000
            _log.info(
                "EOU_DIAG turn_index=%s eou_ms=%.0f transcription_delay_ms=%s "
                "turn_callback_ms=%s transcript_chars=%s turn_mode=%s",
                t.turn_index,
                t.eou_ms,
                None if t.transcription_delay_ms is None else round(t.transcription_delay_ms),
                None if t.turn_callback_ms is None else round(t.turn_callback_ms),
                t.transcript_chars,
                s.turn_mode,
            )
        elif isinstance(m, metrics.STTMetrics):
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.stt_ms = dur * 1000
        elif isinstance(m, metrics.LLMMetrics):
            t.llm_ttft_ms = m.ttft * 1000
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.llm_duration_ms = dur * 1000
            prompt_tokens = getattr(m, "prompt_tokens", None)
            if prompt_tokens is not None:
                t.prompt_tokens = int(prompt_tokens)
                _log.info(
                    "EOU_DIAG turn_index=%s prompt_tokens=%s eou_ms=%s",
                    t.turn_index,
                    t.prompt_tokens,
                    None if t.eou_ms is None else round(t.eou_ms),
                )
        elif isinstance(m, metrics.TTSMetrics):
            t.tts_ttfb_ms = m.ttfb * 1000
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.tts_duration_ms = dur * 1000
            audio_duration = getattr(m, "audio_duration", None)
            if audio_duration is not None:
                t.tts_audio_ms = audio_duration * 1000
        ready_to_close = t.v2v_ready() or (
            t.eou_ms is not None and t.tts_ttfb_ms is not None
        )
        if ready_to_close:
            t.route_ms = (
                float(perf_state["route_ms"]) if perf_state["route_ms"] is not None else None
            )
            t.route = str(perf_state["route"]) if perf_state["route"] is not None else None
            t.context_ms = (
                float(perf_state["context_ms"])
                if perf_state["context_ms"] is not None
                else None
            )
            t.tool_ms = (
                float(perf_state["tool_ms"]) if perf_state["tool_ms"] is not None else None
            )
            if t.v2v_ready():
                v = t.v2v_ms()
                flag = "PASS<800" if v < 800 else "OVER"
                _log.info(
                    "V2V turn %s: eou=%.0fms + ttft=%.0fms + ttfb=%.0fms = %.0fms  [%s]",
                    sid, t.eou_ms, t.llm_ttft_ms, t.tts_ttfb_ms, v, flag,
                )
                asyncio.ensure_future(_record_pythia_latency_forecast(t))
                asyncio.ensure_future(_record_live_skill_kpis(t))
            if barge_state["measured_ms"] is not None:
                t.barge_in_ms = barge_state["measured_ms"]
                barge_state["measured_ms"] = None
            if bench_events_enabled:
                asyncio.ensure_future(
                    _publish_bench_event({"type": "turn_profile", **t.to_dict()})
                )
            if write_profile(t):
                _log.info("LATENCY_PROFILE %s", json.dumps(t.to_dict(), sort_keys=True))
            turns.pop(sid, None)
            for key in perf_state:
                perf_state[key] = None

    if latency_log_enabled():
        # Stamp when the user begins speaking over Sam (agent speaking). Guarded so an unknown
        # event name on a given livekit-agents version is a no-op, never a crash.
        try:
            @session.on("user_state_changed")
            def _on_user_state(ev) -> None:  # type: ignore[no-redef]
                try:
                    _start_barge_overlap(
                        barge_state,
                        ev,
                        other_state=getattr(session, "agent_state", None),
                    )
                except Exception:  # noqa: BLE001
                    _log.debug("barge-in user-state event unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            _log.debug("barge-in capture not available on this livekit-agents version")

        try:
            @session.on("agent_state_changed")
            def _on_agent_state(ev) -> None:  # type: ignore[no-redef]
                try:
                    _start_barge_overlap(
                        barge_state,
                        ev,
                        other_state=getattr(session, "user_state", None),
                    )
                    measured = _finish_barge_overlap(barge_state, ev)
                    if measured is not None:
                        stop_ms = _event_time_ms(ev)
                        detect_ms = stop_ms - measured
                        _log.info(
                            "BARGE_IN inbound_detect_at_ms=%.1f playback_stop_at_ms=%.1f overlap_ms=%.1f target_ms=250 result=%s",
                            detect_ms,
                            stop_ms,
                            measured,
                            "PASS" if measured < 250 else "OVER",
                        )
                except Exception:  # noqa: BLE001
                    _log.debug("barge-in agent-state event unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            _log.debug("agent playback-state capture unavailable")

    rm_client = build_rainmaker_client(s)
    rm_holder["client"] = rm_client

    # Owner gate for Tier-T tools: live voice match, verified JWT role=owner, or
    # an allow-listed SIP caller. The gate fails closed — a connected human is
    # not enough. Verifier is None when voice verify isn't configured.
    verifier = VoiceVerifier.from_settings(s)
    _session_is_owner, owner_gate = build_owner_gate(
        ctx, verifier, sip_owner_numbers=s.sip_owner_numbers
    )
    episode_store = EpisodicMemoryStore() if s.memory_enabled else None
    profile_store = ProfileStore() if s.memory_enabled else None
    artifact_store = ArtifactStore() if s.memory_enabled else None
    artifact_brief = (
        brief_from_artifacts(
            artifact_store.recent(limit=8, exclude_session_id=session_id)
        )
        if artifact_store is not None
        else None
    )
    builder_engagement_id = engagement_id_from_room(room_name)
    continuity_state_ref = [
        ContinuityState(
            engagement_id=builder_engagement_id,
            room_name=room_name,
        )
    ]
    startup_brief = artifact_brief
    pythia_baselines = BaselineStore(episode_store.path) if episode_store is not None else None
    pythia_ledger = ForecastLedger(episode_store.path) if episode_store is not None else None
    skillbuilder_runtime = (
        SkillBuilderRuntime(episode_store.path) if episode_store is not None else None
    )
    pythia_pending: dict[str, int | None] = {"forecast_id": None}
    session_turns: list[tuple[str, str]] = []
    memory_retriever = (
        MemoryRetriever(episode_store, profile_store)
        if episode_store is not None and profile_store is not None
        else None
    )

    async def _record_pythia_latency_forecast(turn: TurnProfile) -> None:
        if (
            pythia_baselines is None
            or pythia_ledger is None
            or artifact_store is None
            or not turn.v2v_ready()
        ):
            return
        pending_id = pythia_pending["forecast_id"]
        if pending_id is not None:
            await pythia_ledger.resolve_async(pending_id, 1.0 if turn.v2v_ms() >= 800 else 0.0)
        forecast = predict_threshold_event(
            "next_turn_latency_over_800",
            "next_turn",
            last_value=turn.v2v_ms(),
            threshold=800.0,
            scale=200.0,
        )
        forecast_id = await pythia_ledger.record_async(forecast)
        pythia_pending["forecast_id"] = forecast_id
        await pythia_baselines.observe_async("next_turn_latency_ms", turn.v2v_ms())
        await artifact_store.add_async(
            Artifact(
                session_id=session_id,
                kind="forecast",
                payload={**forecast.as_artifact(), "forecast_id": forecast_id},
            )
        )

    async def _record_live_skill_kpis(turn: TurnProfile) -> None:
        if skillbuilder_runtime is None or not turn.v2v_ready():
            return
        observed_at = datetime.now(timezone.utc).isoformat()
        values = {
            "v2v_ms": turn.v2v_ms(),
            "eou_ms": float(turn.eou_ms or 0.0),
            "llm_ttft_ms": float(turn.llm_ttft_ms or 0.0),
            "tts_ttfb_ms": float(turn.tts_ttfb_ms or 0.0),
        }
        if turn.barge_in_ms is not None:
            values["barge_in_ms"] = float(turn.barge_in_ms)
        for metric_name, metric_value in values.items():
            await skillbuilder_runtime.record_kpi_async(
                "samuel_live_session",
                KPISnapshot(
                    metric_name=metric_name,
                    metric_value=metric_value,
                    rolling_average=metric_value,
                    period_start=observed_at,
                    period_end=observed_at,
                ),
            )

    if bench_events_enabled:
        @session.on("conversation_item_added")
        def _bench_message(ev) -> None:
            item = getattr(ev, "item", None)
            if getattr(item, "role", None) != "assistant":
                return
            text = str(getattr(item, "text_content", "") or "").strip()
            if text:
                asyncio.ensure_future(
                    _publish_bench_event({"type": "assistant_message", "text": text})
                )

        @session.on("function_tools_executed")
        def _bench_tools(ev) -> None:
            names = [
                str(getattr(call, "name", "") or "")
                for call in (getattr(ev, "function_calls", None) or [])
                if getattr(call, "name", None)
            ]
            if names:
                asyncio.ensure_future(
                    _publish_bench_event({"type": "tool_calls", "names": names})
                )

    @session.on("user_input_transcribed")
    def _note_transcript_chars(ev) -> None:
        if not getattr(ev, "is_final", False):
            return
        text = str(getattr(ev, "transcript", "") or "")
        last_transcript_chars["value"] = len(text.strip())

    async def _persist_owner_turn(
        role: str,
        content: str,
        provenance: dict[str, Any],
    ) -> None:
        result = await rm_client.write_memory_turn(
            session_id=session_id,
            surface="voice",
            role=role,
            content=content,
            provenance={**provenance, "surface_variant": surface},
        )
        if not result.get("ok"):
            _log.debug("canonical owner memory write skipped: %s", result.get("error"))

    @session.on("user_input_transcribed")
    def _remember_user_turn(ev) -> None:
        if not getattr(ev, "is_final", False):
            return
        owner = _session_is_owner()
        asyncio.ensure_future(
            _publish_bench_event(
                {
                    "type": "owner_gate_pass" if owner else "owner_gate_fail",
                }
            )
        )
        text = str(getattr(ev, "transcript", "") or "").strip()
        if not text:
            return
        if is_capped_room(room_name):
            asyncio.ensure_future(_enforce_demo_cap())
        if sam_session.kind == "moderator":
            moderator_runtime.observe(
                str(getattr(ev, "speaker_id", "") or ("host" if owner else "guest")),
                text,
            )
        if not owner and not is_outbound_guest:
            if sam_session.kind == "intake":
                session_turns.append(("guest", text))
            return
        session_turns.append(("user" if owner else "guest", text))
        continuity_state_ref[0] = continuity_state_ref[0].update_turns(session_turns)
        if episode_store is not None and owner:
            asyncio.ensure_future(
                episode_store.append_async(
                    Episode(
                        session_id=session_id,
                        kind="transcript",
                        content=text,
                        speaker_id=getattr(ev, "speaker_id", None),
                        provenance=f"livekit:{session_id}",
                        profile_id="owner",
                    )
                )
            )
        if not owner:
            return
        profile_update = extract_explicit_profile_update(text)
        if profile_store is not None and profile_update is not None:
            asyncio.ensure_future(
                profile_store.upsert_async(
                    ProfileFact(
                        profile_id="owner",
                        key=profile_update.key,
                        value=profile_update.value,
                        provenance=f"explicit_owner_voice:{session_id}",
                        corrected_by="owner" if profile_update.owner_correction else None,
                    ),
                    owner_correction=profile_update.owner_correction,
                )
            )
        asyncio.ensure_future(
            _persist_owner_turn(
                "user",
                text,
                {
                    "source": "sam_worker",
                    "room": session_id,
                    "speaker_id": getattr(ev, "speaker_id", None),
                },
            )
        )
        asyncio.ensure_future(_checkpoint_summary_artifact())

    async def _checkpoint_summary_artifact() -> None:
        if artifact_store is None or not session_turns:
            return
        try:
            summary = _session_close_summary(session_turns)
            artifact_id = await artifact_store.put_async(
                Artifact(
                    session_id=session_id,
                    kind="summary",
                    payload={
                        "text": summary,
                        "reason": "turn_checkpoint",
                        "decisions": list(_session_decisions(session_turns)),
                    },
                )
            )
            await _publish_bench_event(
                {
                    "type": "artifact_checkpoint",
                    "artifact_id": artifact_id,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report without affecting speech
            _log.exception("artifact checkpoint failed")
            await _publish_bench_event(
                {
                    "type": "artifact_checkpoint_failed",
                    "error": type(exc).__name__,
                }
            )

    @session.on("conversation_item_added")
    def _remember_assistant_turn(ev) -> None:
        if not _session_is_owner() and not is_outbound_guest:
            return
        item = getattr(ev, "item", None)
        if getattr(item, "role", None) != "assistant":
            return
        text = str(getattr(item, "text_content", "") or "").strip()
        if text:
            session_turns.append(("assistant", text))
            continuity_state_ref[0] = continuity_state_ref[0].update_turns(session_turns)
            if episode_store is not None:
                asyncio.ensure_future(
                    episode_store.append_async(
                        Episode(
                            session_id=session_id,
                            kind="transcript",
                            content=text,
                            speaker_id="samuel",
                            provenance=f"livekit:{session_id}",
                            profile_id="owner" if _session_is_owner() else None,
                        )
                    )
                )
            asyncio.ensure_future(
                _persist_owner_turn(
                    "assistant",
                    text,
                    {"source": "sam_worker", "room": session_id},
                )
            )
            asyncio.ensure_future(_checkpoint_summary_artifact())

    close_persistence_lock = asyncio.Lock()
    close_persistence_state = {"done": False, "engagement": False}

    async def _notify_owner_call_record() -> None:
        if not is_outbound_guest or not outbound_meta.get("notify_owner", True):
            return
        guest = outbound_meta.get("guest_name") or "guest"
        summary = _session_close_summary(session_turns) if session_turns else "(no speech captured)"
        line = f"Call with {guest}: {summary}"
        try:
            await rm_client.text_me(line[:600])
        except Exception:  # noqa: BLE001
            _log.exception("outbound call record text failed")

    async def _enforce_demo_cap() -> None:
        if not is_capped_room(room_name):
            return
        try:
            result = await rm_client.tick_room(
                room_name, minutes=TURN_MINUTES, tokens=TURN_TOKENS
            )
        except Exception:  # noqa: BLE001
            _log.exception("demo cap tick failed")
            return
        if not should_hangup(result):
            return
        _log.info("DEMO_CAP hangup room=%s error=%s", room_name, result.get("error"))
        try:
            await session.say(GOODBYE, allow_interruptions=False, add_to_chat_ctx=False)
        except Exception:  # noqa: BLE001
            _log.exception("demo cap goodbye failed")
        ctx.shutdown("demo_cap")

    async def _write_voice_engagement() -> None:
        if close_persistence_state["engagement"]:
            return
        if sam_session.kind != "intake" or not session_turns:
            return
        guest = next(
            (
                str(item.display_name or "").strip()
                for item in sam_session.participants
                if item.role == "party" and item.display_name
            ),
            "",
        )
        try:
            await rm_client.write_intake(
                name=guest,
                source="voice-demo",
                answers={
                    "room": room_name,
                    "summary": _session_close_summary(session_turns),
                    "offer": "studio",
                },
            )
            close_persistence_state["engagement"] = True
        except Exception:  # noqa: BLE001
            _log.exception("voice engagement write failed")

    async def _persist_session_close(reason: str) -> None:
        async with close_persistence_lock:
            if close_persistence_state["done"]:
                return
            await _write_voice_engagement()
            if is_outbound_guest:
                await _notify_owner_call_record()
            if episode_store is None or artifact_store is None or not session_turns:
                if is_outbound_guest:
                    close_persistence_state["done"] = True
                return
            if not _session_is_owner() and not is_outbound_guest:
                return
            if close_persistence_state["done"]:
                return
            summary = _session_close_summary(session_turns)
            decisions = _session_decisions(session_turns)
            artifact_id = await artifact_store.put_async(
                Artifact(
                    session_id=session_id,
                    kind="summary",
                    payload={
                        "text": summary,
                        "reason": reason,
                        "decisions": list(decisions),
                    },
                )
            )
            artifact_refs = [f"artifact:{artifact_id}"]
            if moderator_runtime.has_content():
                understanding_id = await artifact_store.put_async(
                    Artifact(
                        session_id=session_id,
                        kind="understanding_map",
                        payload=moderator_runtime.understanding_artifact(),
                    )
                )
                next_steps_id = await artifact_store.put_async(
                    Artifact(
                        session_id=session_id,
                        kind="next_steps",
                        payload=moderator_runtime.next_steps_artifact(),
                    )
                )
                artifact_refs.extend(
                    (f"artifact:{understanding_id}", f"artifact:{next_steps_id}")
                )
                if moderator_runtime.feedback:
                    feedback_id = await artifact_store.put_async(
                        Artifact(
                            session_id=session_id,
                            kind="feedback",
                            payload={
                                "kind": "feedback",
                                "feedback": moderator_runtime.feedback,
                                "names": moderator_runtime.names,
                                "phase": moderator_runtime.phase,
                            },
                        )
                    )
                    artifact_refs.append(f"artifact:{feedback_id}")
            await episode_store.append_async(
                Episode(
                    session_id=session_id,
                    kind="summary",
                    content=summary,
                    summary=summary,
                    decisions=decisions,
                    artifact_refs=tuple(artifact_refs),
                    provenance=f"sam_worker:session_close:{reason}",
                    profile_id="owner",
                )
            )
            if _session_is_owner():
                thread_text = build_thread_summary_text(
                    session_turns,
                    engagement_id=builder_engagement_id,
                    room_name=room_name,
                )
                if thread_text.strip():
                    await rm_client.write_thread_summary(
                        summary=thread_text,
                        session_id=session_id,
                        engagement_id=builder_engagement_id,
                        open_loops=list(extract_open_loops(session_turns)),
                    )
            if skillbuilder_runtime is not None:
                try:
                    snapshot_path = episode_store.path.parent / "sam-hero-snapshot.json"
                    snapshot = await asyncio.to_thread(live_snapshot, skillbuilder_runtime)
                    await asyncio.to_thread(write_snapshot, snapshot_path, snapshot)
                    if allows_skill_approval_sms(
                        sam_session.kind, room_name or session_id
                    ):
                        v2v_values = skillbuilder_runtime.metric_values(
                            "samuel_live_session", "v2v_ms", limit=40
                        )
                        if v2v_values:
                            import statistics

                            candidate = candidate_from_latency(
                                session_id,
                                v2v_p50_ms=float(statistics.median(v2v_values)),
                            )
                            if candidate is not None:
                                run_advisory(
                                    skillbuilder_runtime,
                                    candidate,
                                    reason=candidate.problem_detected,
                                )
                                if candidate.gates.approved_for_adoption:
                                    await rm_client.request_skill_approval(
                                        candidate.candidate_id,
                                        candidate.problem_detected,
                                    )
                        if pythia_ledger is not None:
                            raw = pythia_ledger.calibration_candidate(
                                subject="next_turn_latency_over_800"
                            )
                            if raw is not None:
                                pythia_candidate = candidate_from_pythia_brier(
                                    "next_turn_latency_over_800",
                                    sample_count=int(raw["sample_count"]),
                                    brier=float(raw["brier"]),
                                )
                                # SAM-053: ask the owner once per candidate. Calibration
                                # candidates are advisory, so the ledger's sample floor and
                                # Brier threshold are the filter, not the adoption gates.
                                first_ask = (
                                    skillbuilder_runtime.approval_count(
                                        pythia_candidate.candidate_id
                                    )
                                    == 0
                                )
                                run_advisory(
                                    skillbuilder_runtime,
                                    pythia_candidate,
                                    reason=pythia_candidate.problem_detected,
                                )
                                if first_ask:
                                    await rm_client.request_skill_approval(
                                        pythia_candidate.candidate_id,
                                        pythia_candidate.problem_detected,
                                    )
                except Exception:  # noqa: BLE001
                    _log.exception("skillbuilder close path failed")
            close_persistence_state["done"] = True

    @session.on("close")
    def _remember_session_close(ev) -> None:
        if not _session_is_owner() and not is_outbound_guest:
            return
        reason = str(getattr(ev, "reason", "") or "close")
        asyncio.ensure_future(_persist_session_close(reason))

    async def _persist_on_job_shutdown(reason: str = "job_shutdown") -> None:
        await _persist_session_close(reason or "job_shutdown")

    ctx.add_shutdown_callback(_persist_on_job_shutdown)

    session_logger = SessionLogger(
        room_name=ctx.room.name or ctx.job.id,
        room_sid=getattr(ctx.room, "sid", "") or "",
        is_owner=_session_is_owner,
    )
    if session_logger.active:
        _log.info("session log enabled | path=%s", session_logger.path)

        @session.on("conversation_item_added")
        def _on_conversation_item(ev) -> None:  # type: ignore[no-redef]
            try:
                session_logger.on_conversation_item(ev.item)
            except Exception:  # noqa: BLE001
                _log.debug("session conversation logging failed", exc_info=True)

        @session.on("user_input_transcribed")
        def _on_user_transcript(ev) -> None:  # type: ignore[no-redef]
            try:
                session_logger.on_user_transcript(
                    transcript=ev.transcript,
                    is_final=ev.is_final,
                    speaker_id=getattr(ev, "speaker_id", None),
                )
            except Exception:  # noqa: BLE001
                _log.debug("session transcript logging failed", exc_info=True)

        @session.on("function_tools_executed")
        def _on_tools_executed(ev) -> None:  # type: ignore[no-redef]
            try:
                session_logger.on_tools_executed(ev)
            except Exception:  # noqa: BLE001
                _log.debug("session tool logging failed", exc_info=True)

        @session.on("close")
        def _on_session_close(ev) -> None:  # type: ignore[no-redef]
            try:
                err = getattr(ev, "error", None)
                session_logger.close(
                    reason=str(getattr(ev, "reason", "") or "close"),
                    error=str(err) if err is not None else None,
                )
            except Exception:  # noqa: BLE001
                _log.debug("session close logging failed", exc_info=True)

    tool_registry = _build_tool_registry()
    calendar_turn_state: dict[str, Any] = {}

    def _tool_timing(_name: str, elapsed_ms: float, _cached: bool) -> None:
        perf_state["tool_ms"] = float(perf_state["tool_ms"] or 0.0) + elapsed_ms

    tool_latency_manager = ToolLatencyManager(on_timing=_tool_timing)
    all_tool_names = tool_registry.names()
    all_rm_tools = tool_registry.build_livekit_tools(
        rm_client,
        _session_is_owner,
        function_tool=function_tool,
        owner_refusal=_OWNER_ONLY,
        deps={
            "run_scan_bg": _run_scan_bg,
            "tool_latency_manager": tool_latency_manager,
            "session_id": session_id,
            "room_name": room_name,
            "calendar_turn_state": calendar_turn_state,
        },
    )
    tool_by_name = dict(zip(all_tool_names, all_rm_tools, strict=True))

    def _tools_for_pack(pack_id: str) -> list[Any]:
        selected_names = pack_registry.tools_for(pack_id, all_tool_names)
        if selected_names is None:
            return list(all_rm_tools)
        return [tool_by_name[name] for name in selected_names if name in tool_by_name]

    rm_tools = [] if is_outbound_guest else _tools_for_pack(pack.id)
    rm_mode = "mock" if (s.sam_mock_rm or not s.rm_api_base_url) else "http:" + s.rm_api_base_url
    _log.info(
        "Rainmaker tools enabled (%d) | client=%s | voice_verify=%s",
        len(rm_tools),
        rm_mode,
        "on" if verifier is not None else "off",
    )

    overlay = (pack.persona_overlay or "").strip()
    base_instructions = samuel_instructions()
    instructions = base_instructions
    if overlay:
        instructions = f"{instructions}\n\n{overlay}"

    fast_router = FastIntentRouter()

    async def _direct_execute(decision):
        return await fast_router.execute(decision, rainmaker_client=rm_client)

    async def _publish_command(command: dict) -> None:
        await ctx.room.local_participant.publish_data(
            json.dumps(command),
            reliable=True,
            topic="sam-command",
        )

    async def _context_provider(text: str):
        scope = pack_registry.memory_scope()
        if not _session_is_owner() or not scope["include_owner_remote"]:
            return await assemble_context(
                memory=list,
                profile=dict,
                tools=tool_registry.names,
                permissions=lambda: {"owner": _session_is_owner()},
            )
        local_memory = (
            (
                lambda: memory_retriever.retrieve_async(
                    text,
                    session_id=session_id,
                    profile_id=str(scope["profile_id"]),
                    token_budget=350,
                )
            )
            if memory_retriever is not None
            else list
        )
        local_profile = (
            (lambda: asyncio.to_thread(profile_store.facts, str(scope["profile_id"])))
            if profile_store is not None
            else dict
        )
        memory_cap = owner_memory_token_cap(s)
        snapshot = await assemble_context(
            memory=local_memory,
            profile=local_profile,
            tools=tool_registry.names,
            permissions=lambda: {"owner": True},
            external=lambda: rm_client.get_memory_context(text, token_cap=memory_cap),
            timeout_s=0.75,
        )
        remote = snapshot.external if isinstance(snapshot.external, dict) else {}
        if remote.get("ok") and isinstance(remote.get("items"), list):
            snapshot.memory = [*(snapshot.memory or []), *remote["items"]]
        snapshot.session_summary = continuity_state_ref[0].rolling_summary
        if startup_brief is not None:
            snapshot.external = startup_brief
            await _publish_bench_event(
                {
                    "type": (
                        "prior_artifact_brief"
                        if startup_brief.items
                        else "prior_artifact_brief_empty"
                    ),
                    "count": len(startup_brief.items),
                }
            )
        _log.info(
            "CONTEXT_LATENCY total_ms=%.1f stages=%s errors=%s",
            snapshot.total_ms,
            json.dumps(snapshot.timings_ms, sort_keys=True),
            json.dumps(snapshot.errors, sort_keys=True),
        )
        perf_state["context_ms"] = snapshot.total_ms
        return snapshot

    async def _load_startup_brief() -> None:
        nonlocal startup_brief
        if not _session_is_owner():
            return
        thread_payload = await rm_client.get_thread_summary()
        thread = thread_payload.get("thread") if thread_payload.get("ok") else None
        builder_context = ""
        if builder_engagement_id:
            engagement_payload = await rm_client.get_engagement(builder_engagement_id)
            if engagement_payload.get("ok"):
                builder_context = engagement_fields_for_context(
                    engagement_payload.get("engagement")
                )
        startup_brief = brief_from_thread_summary(
            thread if isinstance(thread, dict) else None,
            artifact_brief=artifact_brief,
            builder_context=builder_context,
        )
        if startup_brief.items:
            _log.info(
                "STARTUP_BRIEF items=%d engagement=%s",
                len(startup_brief.items),
                builder_engagement_id or "-",
            )

    async def _flush_pack(pack_id: str) -> None:
        if artifact_store is None:
            return
        payload: dict[str, Any] = {
            "text": f"Unloaded {pack_id}",
            "pack": pack_id,
            "reason": "pack_unload",
        }
        if pack_id == "moderator" and moderator_runtime.has_content():
            payload["understanding"] = moderator_runtime.understanding_artifact()
            payload["next_steps"] = moderator_runtime.next_steps_artifact()
        artifact_id = await artifact_store.put_async(
            Artifact(session_id=session_id, kind="summary", payload=payload)
        )
        if episode_store is not None:
            await episode_store.append_async(
                Episode(
                    session_id=session_id,
                    kind="pack_unload",
                    content=payload["text"],
                    summary=payload["text"],
                    artifact_refs=(f"artifact:{artifact_id}",),
                    provenance=f"pack:{pack_id}",
                )
            )

    async def _route_session_pack(text: str) -> None:
        previous_pack_id = pack_registry.active_id
        if not sam_session.activate_from_utterance(text):
            return
        try:
            if previous_pack_id != sam_session.pack:
                await _flush_pack(previous_pack_id)
                pack_registry.unload(previous_pack_id)
            active_pack = pack_registry.activate(sam_session.pack)
            active_overlay = (active_pack.persona_overlay or "").strip()
            active_instructions = (
                f"{base_instructions}\n\n{active_overlay}" if active_overlay else base_instructions
            )
            await routed_agent.update_instructions(active_instructions)
            await routed_agent.update_tools(_tools_for_pack(active_pack.id))
            _log.info(
                "SESSION_PACK_ACTIVATED kind=%s pack=%s surface=%s",
                sam_session.kind,
                active_pack.id,
                sam_session.surface,
            )
            await _publish_bench_event(
                {
                    "type": "session_pack_activated",
                    "kind": sam_session.kind,
                    "pack": active_pack.id,
                    "surface": sam_session.surface,
                }
            )
        except Exception:  # noqa: BLE001
            _log.exception("session pack switch failed; keeping prior tools")

    async def _session_turn_override(text: str) -> str | None:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        if re.search(r"\b(pause|hold) (?:this|the) (?:conversation|session)\b", normalized):
            return safety_state.request_pause(sam_session)
        if re.search(r"\b(stop|end|exit) (?:this|the) (?:conversation|session)\b", normalized):
            return safety_state.request_exit(sam_session)
        if sam_session.paused and re.search(
            r"\b(resume|continue|pick (?:this|it) back up)\b", normalized
        ):
            sam_session.resume()
            return "We're back. Please continue when you're ready."
        if sam_session.paused:
            return "We're still paused. Say resume when you're ready to continue."
        if is_outbound_guest:
            pending = take_pending_script(outbound_script, text)
            if pending is not None:
                if pending:
                    _log.info(
                        "outbound first speech=human; delivering script chars=%d",
                        len(pending),
                    )
                else:
                    _log.info("outbound first speech=voicemail; holding script")
                return pending
        return None

    def _route_timing(decision, elapsed_ms: float) -> None:
        perf_state["route"] = decision.route
        perf_state["route_ms"] = elapsed_ms

    async def _commit_calendar() -> str:
        return await handle_commit_calendar_change(rm_client, session_id=session_id)

    history_cap = effective_history_token_cap(
        s,
        is_owner=not is_capped_room(room_name),
        room_name=room_name,
    )

    routed_agent = RoutedSamuelAgent(
        router=fast_router,
        direct_execute=_direct_execute,
        publish_command=_publish_command,
        context_provider=_context_provider,
        performance_report=_route_timing,
        publish_bench=_publish_bench_event,
        session_route=_route_session_pack,
        turn_override=_session_turn_override,
        calendar_turn_state=calendar_turn_state,
        calendar_commit=_commit_calendar,
        history_token_cap=history_cap,
        use_full_tool_set=s.prompt_tool_mode == "stable_full",
        instructions=instructions,
        tools=rm_tools,
    )
    await session.start(agent=routed_agent, room=ctx.room)
    await ctx.connect()
    await _load_startup_brief()
    connected_meta = decode_outbound_metadata(
        pick_outbound_metadata(
            getattr(ctx.room, "metadata", "") or "",
            getattr(getattr(ctx, "job", None), "metadata", "") or "",
        )
    )
    if any(connected_meta.get(key) for key in ("kind", "brief", "spoken", "guest_name")):
        outbound_meta.update(connected_meta)
        outbound_script["spoken"] = str(outbound_meta.get("spoken") or "").strip()

    if (
        is_phone
        and not is_outbound_guest
        and (
            not s.sip_owner_numbers
            or not sip_caller_is_authorized(
                await _wait_for_sip_participants(ctx.room),
                s.sip_owner_numbers,
            )
        )
    ):
        _log.warning("Rejected non-owner SIP caller")
        await session.say(_OWNER_ONLY, allow_interruptions=False)
        ctx.shutdown("SIP caller is not owner-authorized")
        return

    async def _announce_worker() -> None:
        payload = {
            "type": "worker_info",
            "brain": brain,
            "sam_brain_env": s.sam_brain or "",
            "resolved_brain": resolved,
            "turn_mode": s.turn_mode,
            "interruption_mode": s.interruption_mode,
            "stt_model": stt_label,
            "surface": surface,
            "endpoint_min": s.endpoint_min,
            "endpoint_max": s.endpoint_max,
            "history_token_cap": history_cap,
            "owner_history_token_cap": s.owner_history_token_cap,
            "llm_max_completion_tokens": s.llm_max_completion_tokens,
            "git": (os.getenv("RENDER_GIT_COMMIT") or "")[:12],
        }
        await _publish_bench_event(payload)
        await asyncio.sleep(2.0)
        await _publish_bench_event(payload)

    asyncio.ensure_future(_announce_worker())

    tier_state = TierState(tier=2)
    apply_tier_to_session(session, tier_state, s)

    async def _apply_tier_update(tier: int, reason: str = "") -> None:
        try:
            await session.wait_for_idle()
        except Exception:  # noqa: BLE001
            _log.debug("session did not become idle before tier update", exc_info=True)
        if tier_state.update(tier) or reason == "init":
            apply_tier_to_session(session, tier_state, s)

    wire_owner_gate_listeners(ctx.room, owner_gate)
    text_reply_lock = asyncio.Lock()

    builder_dump_applied = {"done": False}

    async def _apply_first_builder_dump(text: str) -> str:
        eid = first_builder_dump_id(room_name, text, already=builder_dump_applied["done"])
        if not eid:
            return ""
        cleaned = (text or "").strip()
        builder_dump_applied["done"] = True
        try:
            spoken = await handle_named_tool(
                rm_client,
                "proposal_apply_summary",
                {"engagement_id": eid, "summary": cleaned},
            )
            _log.info("builder first dump applied engagement=%s chars=%d", eid, len(cleaned))
            if spoken:
                _log.debug("builder first dump result: %s", spoken[:160])
            return eid
        except Exception:  # noqa: BLE001
            builder_dump_applied["done"] = False
            _log.exception("builder first dump apply failed")
            return ""

    async def _ask_builder_gap_after_dump(eid: str, *, add_to_chat: bool = True) -> str:
        reply = await handle_named_tool(
            rm_client,
            "proposal_ask_gap",
            {"engagement_id": eid},
        )
        if reply:
            try:
                await session.say(
                    reply,
                    allow_interruptions=True,
                    add_to_chat_ctx=add_to_chat,
                )
            except Exception:  # noqa: BLE001
                _log.debug("builder gap say failed", exc_info=True)
        return reply or ""

    async def _finish_builder_dump(text: str, *, speak: bool = False) -> str:
        eid = await _apply_first_builder_dump(text)
        if not eid:
            return ""
        if speak:
            return await _ask_builder_gap_after_dump(eid)
        return eid

    async def _generate_text_reply(text: str, request_id: str) -> None:
        """Run the normal Samuel agent/tool path while suppressing TTS entirely."""
        dumped = await _apply_first_builder_dump(text)
        async with text_reply_lock:
            audio_was_enabled = session.output.audio_enabled
            session.output.set_audio_enabled(False)
            try:
                if dumped:
                    reply = await _ask_builder_gap_after_dump(dumped, add_to_chat=False)
                    await ctx.room.local_participant.publish_data(
                        json.dumps(
                            {
                                "type": "assistant_text",
                                "request_id": request_id,
                                "text": reply or "Got it.",
                            }
                        ),
                        reliable=True,
                        topic=CHAT_TOPIC,
                    )
                    return
                handle = session.generate_reply(user_input=text, input_modality="text")
                await handle
                reply = ""
                for item in reversed(handle.chat_items):
                    if getattr(item, "role", None) != "assistant":
                        continue
                    reply = str(getattr(item, "text_content", "") or "").strip()
                    if reply:
                        break
                await ctx.room.local_participant.publish_data(
                    json.dumps(
                        {
                            "type": "assistant_text",
                            "request_id": request_id,
                            "text": reply or "(no reply)",
                        }
                    ),
                    reliable=True,
                    topic=CHAT_TOPIC,
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("chat panel text reply failed")
                await ctx.room.local_participant.publish_data(
                    json.dumps(
                        {
                            "type": "assistant_text",
                            "request_id": request_id,
                            "text": "Samuel could not answer that.",
                            "error": str(exc)[:160],
                        }
                    ),
                    reliable=True,
                    topic=CHAT_TOPIC,
                )
            finally:
                session.output.set_audio_enabled(audio_was_enabled)

    # Start scoring the human mic for the owner voiceprint (no-op when not configured).
    if verifier is not None:
        verifier.attach(ctx.room)

    # SAM-007 / SAM-034: chat panel text + tier updates over the data channel.
    @ctx.room.on("data_received")
    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic == TIER_TOPIC:
            try:
                payload = json.loads(bytes(packet.data).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return
            tier = parse_tier_payload(payload)
            if tier is None:
                return
            reason = str(payload.get("reason") or "")
            _log.debug("tier update from client: tier=%s reason=%s", tier, reason)
            asyncio.ensure_future(_apply_tier_update(tier, reason))
            return

        if packet.topic != CHAT_TOPIC:
            return
        try:
            payload = json.loads(bytes(packet.data).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if payload.get("type") != "text_input":
            return
        text = str(payload.get("text", "")).strip()
        if not text:
            return
        request_id = str(payload.get("request_id") or "")
        _log.info("chat panel text input: %r", text[:80])
        asyncio.ensure_future(_generate_text_reply(text, request_id))

    if is_outbound_guest:
        answered = await wait_for_outbound_answer(ctx.room, timeout_s=90.0)
        if not answered:
            _log.info("outbound guest never answered; skipping greeting")
            ctx.shutdown("outbound unanswered")
            return
        guest = outbound_meta.get("guest_name") or "the recipient"
        spoken = str(outbound_meta.get("spoken") or outbound_script.get("spoken") or "").strip()
        outbound_script["spoken"] = spoken
        _log.info(
            "outbound waiting for first speech guest=%s spoken_chars=%d",
            guest,
            len(spoken),
        )
        return

    # Client must be in the room and subscribed, or the opening plays into silence.
    await _wait_for_sip_participants(ctx.room, timeout_s=8.0)
    await asyncio.sleep(2.5 if should_speak_builder_opening(room_name) else 1.0)
    if should_speak_builder_opening(room_name):
        # Mic is often already live; an interruptible say gets cancelled by VAD.
        builder_heard = {"user": False}

        @session.on("user_input_transcribed")
        def _builder_heard_speech(ev) -> None:
            transcript = str(getattr(ev, "transcript", "") or "").strip()
            if getattr(ev, "is_final", False) and transcript:
                builder_heard["user"] = True
                asyncio.ensure_future(_finish_builder_dump(transcript, speak=True))

        @session.on("conversation_item_added")
        def _builder_heard_item(ev) -> None:
            item = getattr(ev, "item", None)
            role = str(getattr(item, "role", "") or "")
            if role in {"user", "human"}:
                builder_heard["user"] = True
                spoken = _conversation_item_text(item)
                if spoken:
                    asyncio.ensure_future(_finish_builder_dump(spoken, speak=True))

        await session.say(BUILDER_OPENING, allow_interruptions=False)

        async def _builder_silence_reask() -> None:
            await asyncio.sleep(8.0)
            if builder_heard["user"]:
                return
            try:
                await session.say(BUILDER_REASK, allow_interruptions=False)
            except Exception:  # noqa: BLE001
                _log.debug("builder silence reask failed", exc_info=True)

        asyncio.ensure_future(_builder_silence_reask())
    else:
        await session.generate_reply(instructions=greeting_instructions(sam_session.kind))


if __name__ == "__main__":
    start_health_server()
    start_nightly_scheduler()
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
