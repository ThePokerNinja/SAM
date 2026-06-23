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

import livekit.rtc as rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    metrics,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero  # noqa: F401 — register on main thread

from .config import Settings
from .latency import TurnProfile, latency_log_enabled, write_profile
from .personas import SAMUEL
from .stt import build_stt
from .tools.handlers import (
    build_rainmaker_client,
    handle_get_pulse,
    handle_get_research,
    handle_get_scans,
    handle_get_trades,
    handle_queue_research,
)
from .voice_verify import VoiceVerifier

# Spoken refusal when a Tier-T (trigger) tool is called by a non-owner session.
_OWNER_ONLY = (
    "I can only do that for the owner, and I didn't recognize your voice just now. "
    "I can still read you the scans, the pulse, trades, or research."
)


async def _run_scan_bg(client) -> None:
    """Fire the ~60s scan without blocking the voice turn; results land in /scan/latest."""
    try:
        res = await client.run_scan()
        if not res.get("ok"):
            _log.warning("background scan run failed: %s", res.get("error"))
    except Exception:  # noqa: BLE001
        _log.exception("background scan run crashed")


def _build_rainmaker_tools(client, is_owner) -> list:
    """LiveKit function tools bound to ``client``. Defined at module scope so the
    ``RunContext`` annotation resolves against this module's globals (Python 3.14
    evaluates annotations lazily; LiveKit calls get_type_hints on the tool fn).

    ``is_owner`` is a zero-arg callable gating Tier-T (trigger) tools."""

    @function_tool
    async def get_scans(context: RunContext) -> str:
        """Get the latest Rainmaker scan picks (ticker symbols and any new tickers today).
        Use this whenever the user asks about scans, picks, watchlist, or what's on the board."""
        return await handle_get_scans(client, limit=5)

    @function_tool
    async def get_pulse(context: RunContext) -> str:
        """Get the current market pulse / morning bias (regime, lean, confidence).
        Use this for any question about the market read, mood, regime, or how the tape looks."""
        return await handle_get_pulse(client)

    @function_tool
    async def get_trades(context: RunContext) -> str:
        """Get recent realized (closed) Rainmaker trades.
        Use this for questions about trades, positions, P/L, or recent performance."""
        return await handle_get_trades(client, status=None)

    @function_tool
    async def get_research(context: RunContext) -> str:
        """Read the most recent Rainmaker research digest (completed research ideas + summaries).
        Use this when the user asks about research, the latest findings, or what's been researched."""
        return await handle_get_research(client, limit=3)

    @function_tool
    async def run_scan(context: RunContext) -> str:
        """Trigger a fresh Rainmaker scan now. Owner only. Use only when the owner explicitly
        asks to run, refresh, or re-run the scan. It starts the scan and returns immediately."""
        if not is_owner():
            return _OWNER_ONLY
        asyncio.ensure_future(_run_scan_bg(client))
        return (
            "Scan started - it takes about a minute. Ask me for the latest picks shortly "
            "and I'll read what it found."
        )

    @function_tool
    async def queue_research(context: RunContext, topic: str) -> str:
        """Queue a Rainmaker research request on a topic or ticker. Owner only. Use when the owner
        asks you to research something. `topic` is what to research (a company, ticker, or question)."""
        if not is_owner():
            return _OWNER_ONLY
        return await handle_queue_research(client, topic)

    return [get_scans, get_pulse, get_trades, get_research, run_scan, queue_research]

load_dotenv()
_log = logging.getLogger("sam.agent")


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _participant_is_owner(ctx: JobContext) -> bool:
    """Fallback owner check: a remote participant carrying role=owner from the token mint
    (set by the token server when the portal access key is configured AND matched)."""
    try:
        for p in ctx.room.remote_participants.values():
            attrs = getattr(p, "attributes", None) or {}
            if attrs.get("role") == "owner":
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _build_llm(s: Settings):
    brain = s.sam_brain  # explicit override wins
    if brain == "groq" or (not brain and s.groq_api_key and not s.openai_api_key):
        return openai.LLM(model=s.groq_model, base_url=s.groq_base_url, api_key=s.groq_api_key)
    # Default: OpenAI (higher TPM, tool calling, strict schema support).
    return openai.LLM(model=s.openai_model, base_url=s.openai_base_url, api_key=s.openai_api_key)


async def entrypoint(ctx: JobContext) -> None:
    s = Settings.from_env()
    _use_groq = s.sam_brain == "groq" or (not s.sam_brain and s.groq_api_key and not s.openai_api_key)
    brain = ("groq:" + s.groq_model) if _use_groq else ("openai:" + s.openai_model)
    stt = build_stt(s)
    stt_label = s.stt_model if not s.deepgram_api_key else f"deepgram/{s.stt_model.removeprefix('deepgram/')}"
    _log.info("Samuel starting | brain=%s | stt=%s | voice=%s", brain, stt_label, s.voice_ids["samuel"][:6])

    # Barge-in sensitivity. Defaults are deliberately less twitchy than LiveKit's
    # (0.5s / 0 words): require ~0.8s of sustained speech AND >=2 recognized words
    # before cutting Sam off, so coughs, "uh", room noise, and speaker echo don't
    # interrupt mid-sentence. Tune from .env without code changes.
    interrupt_dur = float(os.getenv("SAM_INTERRUPT_MIN_DURATION", "0.8"))
    interrupt_words = int(os.getenv("SAM_INTERRUPT_MIN_WORDS", "2"))

    # Endpointing = how long Sam waits in silence before deciding you're done and
    # replying. This dominates perceived latency (brain+TTS are ~450ms; the default
    # turn detector was sitting on ~2.5s of EOU). min = floor after a confident
    # end-of-turn; max = ceiling when it's unsure you've finished. Tune from .env.
    endpoint_min = float(os.getenv("SAM_ENDPOINTING_MIN", "0.3"))
    endpoint_max = float(os.getenv("SAM_ENDPOINTING_MAX", "1.2"))

    session = AgentSession(
        stt=stt,
        llm=_build_llm(s),
        tts=elevenlabs.TTS(
            model=s.elevenlabs_model,
            voice_id=s.voice_ids["samuel"],
            api_key=s.elevenlabs_api_key,
        ),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
        min_interruption_duration=interrupt_dur,
        min_interruption_words=interrupt_words,
        min_endpointing_delay=endpoint_min,
        max_endpointing_delay=endpoint_max,
    )

    # Per-turn latency profiles (PDF Phase 1 / ADR-24). The headline v2v log line below is
    # unchanged; TurnProfile records the full per-stage breakdown and, when SAM_LATENCY_LOG=1,
    # appends a JSONL row for offline tier analysis (see bench/latency_profile.py).
    turns: dict[str, TurnProfile] = {}
    # Best-effort barge-in capture: when the user starts speaking while Sam is talking, stamp t0;
    # the delay is attached to the next completed profile. None when never triggered (never faked).
    barge_state = {"t0_ms": None}  # type: dict[str, float | None]

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        m = ev.metrics
        sid = getattr(m, "speech_id", None)
        if not sid:
            return
        t = turns.setdefault(sid, TurnProfile(speech_id=sid))
        if isinstance(m, metrics.EOUMetrics):
            t.eou_ms = m.end_of_utterance_delay * 1000
            td = getattr(m, "transcription_delay", None)
            if td is not None:
                t.transcription_delay_ms = td * 1000
        elif isinstance(m, metrics.STTMetrics):
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.stt_ms = dur * 1000
        elif isinstance(m, metrics.LLMMetrics):
            t.llm_ttft_ms = m.ttft * 1000
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.llm_duration_ms = dur * 1000
        elif isinstance(m, metrics.TTSMetrics):
            t.tts_ttfb_ms = m.ttfb * 1000
            dur = getattr(m, "duration", None)
            if dur is not None:
                t.tts_duration_ms = dur * 1000
        if t.v2v_ready():
            v = t.v2v_ms()
            flag = "PASS<800" if v <= 800 else ("p95<1500" if v <= 1500 else "OVER")
            _log.info(
                "V2V turn %s: eou=%.0fms + ttft=%.0fms + ttfb=%.0fms = %.0fms  [%s]",
                sid, t.eou_ms, t.llm_ttft_ms, t.tts_ttfb_ms, v, flag,
            )
            # Attach any pending barge-in delay, then persist the full profile when enabled.
            if barge_state["t0_ms"] is not None:
                t.barge_in_ms = max(0.0, (time.time() * 1000.0) - barge_state["t0_ms"])
                barge_state["t0_ms"] = None
            write_profile(t)
            turns.pop(sid, None)

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
                    pass
        except Exception:  # noqa: BLE001
            _log.debug("barge-in capture not available on this livekit-agents version")

    rm_client = build_rainmaker_client(s)

    # Owner gate for Tier-T tools: live voice match (primary) OR access-key owner
    # attribute on the token (fallback). Verifier is None when voice verify isn't configured.
    verifier = VoiceVerifier.from_settings(s)

    def _session_is_owner() -> bool:
        if verifier is not None and verifier.is_owner():
            return True
        return _participant_is_owner(ctx)

    rm_tools = _build_rainmaker_tools(rm_client, _session_is_owner)
    rm_mode = "mock" if (s.sam_mock_rm or not s.rm_api_base_url) else "http:" + s.rm_api_base_url
    _log.info(
        "Rainmaker tools enabled (%d) | client=%s | voice_verify=%s",
        len(rm_tools),
        rm_mode,
        "on" if verifier is not None else "off",
    )

    instructions = (
        SAMUEL.system_hint
        + "\n\nTOOLS: For any question about scans/picks, the market pulse or regime, or "
        "trades/positions/P&L, you MUST call the matching tool (get_scans, get_pulse, "
        "get_trades) and speak only what it returns. Never answer these from memory."
    )

    await session.start(agent=Agent(instructions=instructions, tools=rm_tools), room=ctx.room)
    await ctx.connect()

    # Start scoring the human mic for the owner voiceprint (no-op when not configured).
    if verifier is not None:
        verifier.attach(ctx.room)

    # SAM-007: receive typed messages from the chat panel and reply in voice.
    # Client sends: {type: "text_input", text: "<message>"} as reliable data on topic "sam-chat".
    @ctx.room.on("data_received")
    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != "sam-chat":
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
