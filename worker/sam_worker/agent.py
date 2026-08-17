"""Real LiveKit agent (Phase 5b) - Samuel, with per-turn voice-to-voice latency logging.

Pipeline (ADR-1/3/4/5):
  STT : LiveKit Inference by default; Deepgram direct when DEEPGRAM_API_KEY is set (SAM_STT=deepgram).
  LLM : OpenAI-compatible client pointed at Groq (live tier, llama-3.1-8b-instant).
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
import sys
import time

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
    metrics,
)
from livekit.plugins import (  # noqa: F401 — register on main thread
    deepgram,
    elevenlabs,
    openai,
    silero,
)

from .config import Settings, resolve_brain
from .context import assemble_context
from .latency import TurnProfile, latency_log_enabled, write_profile
from .memory import Episode, EpisodicMemoryStore, MemoryRetriever, ProfileStore
from .owner_gate import build_owner_gate, wire_owner_gate_listeners
from .prompt_budget import samuel_instructions
from .router import FastIntentRouter, RoutedSamuelAgent
from .session_log import SessionLogger
from .stt import build_stt
from .tier import TierState
from .tier_session import apply_tier_to_session, parse_tier_payload
from .tool_latency import ToolLatencyManager
from .tools.handlers import build_rainmaker_client
from .tools.rainmaker_registry import register_rainmaker_tools
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


load_dotenv()
_log = logging.getLogger("sam.agent")


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _build_llm(s: Settings):
    if resolve_brain(s) == "groq":
        return openai.LLM(model=s.groq_model, base_url=s.groq_base_url, api_key=s.groq_api_key)
    return openai.LLM(model=s.openai_model, base_url=s.openai_base_url, api_key=s.openai_api_key)


async def entrypoint(ctx: JobContext) -> None:
    # Dedicated full-audio mode experiments run an in-process agent in these rooms.
    # The production worker must not create a second Samuel participant there.
    if (ctx.room.name or "").startswith("sam-wave8-embedded-"):
        _log.info("Skipping embedded benchmark room dispatch")
        return
    s = Settings.from_env()
    resolved = resolve_brain(s)
    brain = (resolved + ":" + (s.groq_model if resolved == "groq" else s.openai_model))
    if (s.sam_brain or "").strip().lower() == "openai" and resolved == "groq":
        _log.info("SAM_BRAIN=openai treated as stale Wave 8.1 pin; live default is groq")
    stt = build_stt(s)
    stt_label = s.stt_model if not s.deepgram_api_key else f"deepgram/{s.stt_model.removeprefix('deepgram/')}"
    _log.info(
        "Samuel starting | brain=%s | stt=%s | turn=%s | endpoint=%.2f/%.2f | voice=%s",
        brain,
        stt_label,
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
        vad=ctx.proc.userdata["vad"],
        turn_handling=build_turn_handling(s),
    )

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
        if t.v2v_ready():
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
            v = t.v2v_ms()
            flag = "PASS<800" if v < 800 else "OVER"
            _log.info(
                "V2V turn %s: eou=%.0fms + ttft=%.0fms + ttfb=%.0fms = %.0fms  [%s]",
                sid, t.eou_ms, t.llm_ttft_ms, t.tts_ttfb_ms, v, flag,
            )
            if barge_state["measured_ms"] is not None:
                t.barge_in_ms = barge_state["measured_ms"]
                barge_state["measured_ms"] = None
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
                    new = getattr(ev, "new_state", None)
                    agent_state = getattr(session, "agent_state", None)
                    if new == "speaking" and agent_state == "speaking":
                        barge_state["t0_ms"] = time.time() * 1000.0
                except Exception:  # noqa: BLE001
                    _log.debug("barge-in user-state event unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            _log.debug("barge-in capture not available on this livekit-agents version")

        try:
            @session.on("agent_state_changed")
            def _on_agent_state(ev) -> None:  # type: ignore[no-redef]
                try:
                    if (
                        getattr(ev, "old_state", None) == "speaking"
                        and getattr(ev, "new_state", None) != "speaking"
                        and barge_state["t0_ms"] is not None
                    ):
                        barge_state["measured_ms"] = max(
                            0.0, (time.time() * 1000.0) - barge_state["t0_ms"]
                        )
                        barge_state["t0_ms"] = None
                except Exception:  # noqa: BLE001
                    _log.debug("barge-in agent-state event unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            _log.debug("agent playback-state capture unavailable")

    rm_client = build_rainmaker_client(s)

    # Owner gate for Tier-T tools: live voice match (primary) OR access-key owner
    # attribute on the token (fallback). Verifier is None when voice verify isn't configured.
    verifier = VoiceVerifier.from_settings(s)
    _session_is_owner, owner_gate = build_owner_gate(ctx, verifier)
    episode_store = EpisodicMemoryStore() if s.memory_enabled else None
    profile_store = ProfileStore() if s.memory_enabled else None
    memory_retriever = (
        MemoryRetriever(episode_store, profile_store)
        if episode_store is not None and profile_store is not None
        else None
    )
    session_id = ctx.room.name or ctx.job.id
    bench_events_enabled = session_id.startswith("sam-wave8-")

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

    if episode_store is not None:
        @session.on("user_input_transcribed")
        def _remember_user_turn(ev) -> None:
            if not getattr(ev, "is_final", False) or not _session_is_owner():
                return
            text = str(getattr(ev, "transcript", "") or "").strip()
            if text:
                asyncio.ensure_future(
                    episode_store.append_async(
                        Episode(
                            session_id=session_id,
                            kind="transcript",
                            content=text,
                            speaker_id=getattr(ev, "speaker_id", None),
                            provenance=f"livekit:{session_id}",
                        )
                    )
                )

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
                pass

        @session.on("user_input_transcribed")
        def _on_user_transcript(ev) -> None:  # type: ignore[no-redef]
            try:
                session_logger.on_user_transcript(
                    transcript=ev.transcript,
                    is_final=ev.is_final,
                    speaker_id=getattr(ev, "speaker_id", None),
                )
            except Exception:  # noqa: BLE001
                pass

        @session.on("function_tools_executed")
        def _on_tools_executed(ev) -> None:  # type: ignore[no-redef]
            try:
                session_logger.on_tools_executed(ev)
            except Exception:  # noqa: BLE001
                pass

        @session.on("close")
        def _on_session_close(ev) -> None:  # type: ignore[no-redef]
            try:
                err = getattr(ev, "error", None)
                session_logger.close(
                    reason=str(getattr(ev, "reason", "") or "close"),
                    error=str(err) if err is not None else None,
                )
            except Exception:  # noqa: BLE001
                pass

    tool_registry = _build_tool_registry()
    def _tool_timing(_name: str, elapsed_ms: float, _cached: bool) -> None:
        perf_state["tool_ms"] = float(perf_state["tool_ms"] or 0.0) + elapsed_ms

    tool_latency_manager = ToolLatencyManager(on_timing=_tool_timing)
    rm_tools = tool_registry.build_livekit_tools(
        rm_client,
        _session_is_owner,
        function_tool=function_tool,
        owner_refusal=_OWNER_ONLY,
        deps={
            "run_scan_bg": _run_scan_bg,
            "tool_latency_manager": tool_latency_manager,
        },
    )
    rm_mode = "mock" if (s.sam_mock_rm or not s.rm_api_base_url) else "http:" + s.rm_api_base_url
    _log.info(
        "Rainmaker tools enabled (%d) | client=%s | voice_verify=%s",
        len(rm_tools),
        rm_mode,
        "on" if verifier is not None else "off",
    )

    instructions = samuel_instructions()

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
        if memory_retriever is None or profile_store is None or not _session_is_owner():
            return await assemble_context(
                memory=list,
                profile=dict,
                tools=tool_registry.names,
                permissions=lambda: {"owner": _session_is_owner()},
            )
        snapshot = await assemble_context(
            memory=lambda: memory_retriever.retrieve_async(
                text,
                session_id=session_id,
                profile_id="owner",
                token_budget=600,
            ),
            profile=lambda: asyncio.to_thread(profile_store.facts, "owner"),
            tools=tool_registry.names,
            permissions=lambda: {"owner": True},
            timeout_s=0.75,
        )
        _log.info(
            "CONTEXT_LATENCY total_ms=%.1f stages=%s errors=%s",
            snapshot.total_ms,
            json.dumps(snapshot.timings_ms, sort_keys=True),
            json.dumps(snapshot.errors, sort_keys=True),
        )
        perf_state["context_ms"] = snapshot.total_ms
        return snapshot

    def _route_timing(decision, elapsed_ms: float) -> None:
        perf_state["route"] = decision.route
        perf_state["route_ms"] = elapsed_ms

    routed_agent = RoutedSamuelAgent(
        router=fast_router,
        direct_execute=_direct_execute,
        publish_command=_publish_command,
        context_provider=_context_provider,
        performance_report=_route_timing,
        publish_bench=_publish_bench_event,
        history_token_cap=s.history_token_cap,
        instructions=instructions,
        tools=rm_tools,
    )
    await session.start(agent=routed_agent, room=ctx.room)
    await ctx.connect()
    await _publish_bench_event(
        {
            "type": "worker_info",
            "brain": brain,
            "sam_brain_env": s.sam_brain or "",
            "resolved_brain": resolved,
            "endpoint_min": s.endpoint_min,
            "endpoint_max": s.endpoint_max,
            "history_token_cap": s.history_token_cap,
            "git": (os.getenv("RENDER_GIT_COMMIT") or "")[:12],
        }
    )

    tier_state = TierState(tier=2)
    apply_tier_to_session(session, tier_state, s)

    async def _apply_tier_update(tier: int, reason: str = "") -> None:
        try:
            await session.wait_for_idle()
        except Exception:  # noqa: BLE001
            pass
        if tier_state.update(tier) or reason == "init":
            apply_tier_to_session(session, tier_state, s)

    wire_owner_gate_listeners(ctx.room, owner_gate)

    # Start scoring the human mic for the owner voiceprint (no-op when not configured).
    if verifier is not None:
        verifier.attach(ctx.room)

    # SAM-007 / SAM-034: chat panel text + tier updates over the data channel.
    @ctx.room.on("data_received")
    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic == TIER_TOPIC:
            try:
                payload = json.loads(bytes(packet.data).decode("utf-8"))
            except Exception:
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
        except Exception:
            return
        if payload.get("type") != "text_input":
            return
        text = str(payload.get("text", "")).strip()
        if not text:
            return
        _log.info("chat panel text input: %r", text[:80])
        asyncio.ensure_future(session.generate_reply(user_input=text))

    await session.generate_reply(
        instructions=(
            "Greet the user warmly as Samuel in one short spoken sentence, then ask how "
            "you can help. Do not promise any capabilities, pricing, or actions in the greeting."
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
