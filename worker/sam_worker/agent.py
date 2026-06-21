"""Real LiveKit agent (Phase 5b) - Samuel, with per-turn voice-to-voice latency logging.

Pipeline (ADR-1/3/4/5):
  STT : LiveKit Inference (string model, billed via LiveKit Cloud) - no separate STT key.
  LLM : OpenAI-compatible client pointed at Groq (live tier, llama-3.1-8b-instant).
  TTS : ElevenLabs Flash v2.5 streaming (our key), Samuel's voice.
  VAD : Silero (prewarmed). Preemptive generation on.

Run (needs worker/.env with LIVEKIT_*, GROQ_API_KEY or OPENAI_API_KEY, ELEVENLABS_API_KEY, SAM_VOICE_ID):
  python -m sam_worker.agent console   # local mic/speaker, fastest way to hear Sam + read v2v
  python -m sam_worker.agent dev       # register a worker with LiveKit Cloud; join via Agents Playground

Per turn it logs: EOU delay + LLM TTFT + TTS TTFB = v2v, flagged against the 800ms KPI.
"""

from __future__ import annotations

import logging
import os
import sys

# Windows consoles default to cp1252; LiveKit's CLI banner prints an emoji that crashes
# the charmap codec. Force UTF-8 on our streams before any livekit import prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    WorkerOptions,
    cli,
    inference,
    metrics,
)
from livekit.plugins import elevenlabs, openai, silero

from .config import Settings
from .personas import SAMUEL

load_dotenv()
_log = logging.getLogger("sam.agent")


class _Turn:
    """Accumulates the three latency components for one speech_id."""

    __slots__ = ("eou", "ttft", "ttfb")

    def __init__(self) -> None:
        self.eou: float | None = None
        self.ttft: float | None = None
        self.ttfb: float | None = None

    def ready(self) -> bool:
        return self.eou is not None and self.ttft is not None and self.ttfb is not None

    def v2v(self) -> float:
        return (self.eou or 0) + (self.ttft or 0) + (self.ttfb or 0)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def _build_llm(s: Settings):
    if s.groq_api_key:
        return openai.LLM(model=s.groq_model, base_url=s.groq_base_url, api_key=s.groq_api_key)
    return openai.LLM(model=s.openai_model, base_url=s.openai_base_url, api_key=s.openai_api_key)


async def entrypoint(ctx: JobContext) -> None:
    s = Settings.from_env()
    brain = "groq:" + s.groq_model if s.groq_api_key else "openai:" + s.openai_model
    _log.info("Samuel starting | brain=%s | stt=%s | voice=%s", brain, s.stt_model, s.voice_ids["samuel"][:6])

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
        stt=inference.STT(model=s.stt_model),
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

    turns: dict[str, _Turn] = {}

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        m = ev.metrics
        sid = getattr(m, "speech_id", None)
        if not sid:
            return
        t = turns.setdefault(sid, _Turn())
        if isinstance(m, metrics.EOUMetrics):
            t.eou = m.end_of_utterance_delay * 1000
        elif isinstance(m, metrics.LLMMetrics):
            t.ttft = m.ttft * 1000
        elif isinstance(m, metrics.TTSMetrics):
            t.ttfb = m.ttfb * 1000
        if t.ready():
            v = t.v2v()
            flag = "PASS<800" if v <= 800 else ("p95<1500" if v <= 1500 else "OVER")
            _log.info(
                "V2V turn %s: eou=%.0fms + ttft=%.0fms + ttfb=%.0fms = %.0fms  [%s]",
                sid, t.eou, t.ttft, t.ttfb, v, flag,
            )
            turns.pop(sid, None)

    await session.start(agent=Agent(instructions=SAMUEL.system_hint), room=ctx.room)
    await ctx.connect()
    await session.generate_reply(
        instructions="Greet the user warmly as Samuel in one short sentence, then ask how you can help."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
