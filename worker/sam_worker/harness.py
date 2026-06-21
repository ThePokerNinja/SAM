"""Phase 5 local latency harness (no WebRTC).

Two measurement modes against real vendors:

  rest : brain time-to-first-sentence (streaming LLM) + ElevenLabs REST streaming TTFB.
         Conservative "wait for a sentence, then speak" baseline.
  ws   : ElevenLabs WebSocket INPUT-streaming TTS - brain tokens are piped into the TTS
         socket as they arrive, so audio starts while the brain is still talking. This is
         the target architecture. v2v = request start -> first audio chunk.

Both exclude STT finalization, turn-detection, and WebRTC transport (room-only, measured in 5b).

Brains are OpenAI-compatible, so we A/B any configured provider (OpenAI gpt-4o-mini, Groq
llama-3.1-8b-instant, ...) through the identical pipeline.

Run:
  python -m sam_worker --bench --turns 10            # A/B all brains, ws + rest
  python -m sam_worker --bench --mode ws --turns 10  # ws only
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from .config import Settings
from .personas import SAMUEL

_PROMPTS = [
    "Sam, what's the morning read?",
    "How is NVDA setting up today?",
    "Give me the one-line team brief.",
    "What's the biggest risk on the board right now?",
    "Should I be adding or trimming here?",
]

_ELEVEN_REST = "https://api.elevenlabs.io/v1/text-to-speech"
_SENTENCE_ENDERS = (".", "!", "?")
_SYSTEM = SAMUEL.system_hint + " Reply in one or two short sentences."


@dataclass
class BrainCfg:
    name: str
    base_url: str
    api_key: str
    model: str


def _brains(settings: Settings) -> list[BrainCfg]:
    out: list[BrainCfg] = []
    if settings.openai_api_key:
        out.append(BrainCfg("openai", settings.openai_base_url, settings.openai_api_key, settings.openai_model))
    if settings.groq_api_key:
        out.append(BrainCfg("groq", settings.groq_base_url, settings.groq_api_key, settings.groq_model))
    return out


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int((p / 100.0) * len(s)))
    return s[idx]


def _first_sentence(buf: str) -> str | None:
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_ENDERS and i >= 8:
            return buf[: i + 1]
    if len(buf.split()) >= 12:
        return buf
    return None


async def _brain_tokens(client, cfg: BrainCfg, prompt: str):
    """Yield ('first_token', ms) once, then ('token', delta) per chunk, then ('done', full)."""
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    body = {
        "model": cfg.model,
        "stream": True,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    t0 = time.perf_counter()
    first = False
    full = ""
    async with client.stream("POST", url, headers=headers, json=body) as resp:
        if resp.status_code != 200:
            detail = (await resp.aread())[:200]
            raise RuntimeError(f"{cfg.name} {resp.status_code}: {detail!r}")
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content", "")
            except (KeyError, IndexError, json.JSONDecodeError):
                continue
            if not delta:
                continue
            if not first:
                first = True
                yield ("first_token", (time.perf_counter() - t0) * 1000)
            full += delta
            yield ("token", delta)
    yield ("done", full)


async def _tts_rest_ttfb(client, settings: Settings, text: str) -> float:
    voice_id = settings.voice_ids.get("samuel", "")
    url = f"{_ELEVEN_REST}/{voice_id}/stream"
    params = {"optimize_streaming_latency": "3", "output_format": "mp3_44100_128"}
    headers = {"xi-api-key": settings.elevenlabs_api_key, "content-type": "application/json"}
    body = {
        "text": text,
        "model_id": settings.elevenlabs_model,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "use_speaker_boost": True},
    }
    t0 = time.perf_counter()
    async with client.stream("POST", url, params=params, headers=headers, json=body) as resp:
        if resp.status_code != 200:
            detail = (await resp.aread())[:200]
            raise RuntimeError(f"ElevenLabs REST {resp.status_code}: {detail!r}")
        async for chunk in resp.aiter_bytes():
            if chunk:
                return (time.perf_counter() - t0) * 1000
    return 0.0


async def _turn_rest(client, settings: Settings, cfg: BrainCfg, prompt: str) -> dict:
    t0 = time.perf_counter()
    brain_ttft = None
    buf = ""
    sentence = None
    async for ev, val in _brain_tokens(client, cfg, prompt):
        if ev == "first_token":
            brain_ttft = val
        elif ev == "token":
            buf += val
            sentence = _first_sentence(buf)
            if sentence:
                break
        elif ev == "done":
            sentence = buf
            break
    if not sentence:
        raise RuntimeError("brain produced no text")
    brain_to_sentence = (time.perf_counter() - t0) * 1000
    tts_ttfb = await _tts_rest_ttfb(client, settings, sentence)
    return {"brain_ttft": brain_ttft or 0.0, "tts": tts_ttfb, "v2v": brain_to_sentence + tts_ttfb}


async def _turn_ws(client, settings: Settings, cfg: BrainCfg, prompt: str) -> dict:
    """Pipe brain tokens into the ElevenLabs WS as they stream; time to first audio chunk."""
    from websockets.asyncio.client import connect

    voice_id = settings.voice_ids.get("samuel", "")
    uri = (
        f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
        f"?model_id={settings.elevenlabs_model}&output_format=mp3_44100_128"
    )
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    t0 = time.perf_counter()
    brain_ttft = None
    first_audio = None

    async with connect(uri, additional_headers=headers, max_size=None) as ws:
        # BOS: voice settings + a small first chunk schedule so audio starts ASAP.
        await ws.send(
            json.dumps(
                {
                    "text": " ",
                    "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "use_speaker_boost": True},
                    "generation_config": {"chunk_length_schedule": [50, 120, 160, 290]},
                }
            )
        )

        async def pump():
            nonlocal brain_ttft
            async for ev, val in _brain_tokens(client, cfg, prompt):
                if ev == "first_token":
                    brain_ttft = val
                elif ev == "token":
                    await ws.send(json.dumps({"text": val, "try_trigger_generation": True}))
                elif ev == "done":
                    await ws.send(json.dumps({"text": ""}))  # flush + close input

        pump_task = asyncio.create_task(pump())
        try:
            async for msg in ws:
                data = json.loads(msg)
                if data.get("audio"):
                    first_audio = (time.perf_counter() - t0) * 1000
                    break
        finally:
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    if first_audio is None:
        raise RuntimeError("no audio from WS")
    return {"brain_ttft": brain_ttft or 0.0, "tts": 0.0, "v2v": first_audio}


def _missing(settings: Settings) -> list[str]:
    miss = []
    if not settings.elevenlabs_api_key:
        miss.append("ELEVENLABS_API_KEY")
    if not settings.voice_ids.get("samuel"):
        miss.append("SAM_VOICE_ID")
    if not (settings.openai_api_key or settings.groq_api_key):
        miss.append("OPENAI_API_KEY or GROQ_API_KEY")
    return miss


async def _run_one(client, settings, cfg, mode, prompt):
    if mode == "ws":
        return await _turn_ws(client, settings, cfg, prompt)
    return await _turn_rest(client, settings, cfg, prompt)


async def _bench_combo(client, settings, cfg: BrainCfg, mode: str, turns: int) -> None:
    label = f"{cfg.name}/{cfg.model}  [{mode}]"
    try:
        await _run_one(client, settings, cfg, mode, "Warm up please.")  # warmup, uncounted
    except Exception as exc:  # noqa: BLE001
        print(f"\n{label}: WARMUP FAILED -> {exc}")
        return
    v2v: list[float] = []
    ttft: list[float] = []
    for i in range(turns):
        prompt = _PROMPTS[i % len(_PROMPTS)]
        try:
            r = await _run_one(client, settings, cfg, mode, prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"  {label} turn {i + 1}: ERROR {exc}")
            continue
        v2v.append(r["v2v"])
        ttft.append(r["brain_ttft"])
    if not v2v:
        print(f"\n{label}: no successful turns")
        return
    p50, p95 = _percentile(v2v, 50), _percentile(v2v, 95)
    flag = "PASS<800 p50" if p50 <= 800 else ("p95<1500 only" if p95 <= 1500 else "OVER")
    print(
        f"\n{label}\n"
        f"  v2v   p50={p50:6.0f}ms  p95={p95:6.0f}ms  min={min(v2v):.0f}  max={max(v2v):.0f}  n={len(v2v)}  -> {flag}\n"
        f"  brain ttft p50={_percentile(ttft, 50):6.0f}ms  (p95={_percentile(ttft, 95):.0f}ms)"
    )


async def run_bench(turns: int = 10, mode: str = "ab") -> int:
    try:
        import httpx  # noqa: F401
    except ImportError:
        print("Install httpx first:  pip install httpx")
        return 2
    import httpx

    settings = Settings.from_env()
    miss = _missing(settings)
    if miss:
        print("Missing env (put these in worker/.env): " + ", ".join(miss))
        return 2

    brains = _brains(settings)
    modes = ["rest", "ws"] if mode == "ab" else [mode]
    print("S.A.M. Phase 5 latency harness (brain + TTS core, no transport)")
    print(f"brains: {', '.join(f'{b.name}:{b.model}' for b in brains)}")
    print(f"tts={settings.elevenlabs_model} voice={settings.voice_ids['samuel'][:6]}...  modes={modes}")
    print("KPI: v2v <= 800ms p50 / <= 1500ms p95 (excludes STT + transport)")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for m in modes:
            for cfg in brains:
                await _bench_combo(client, settings, cfg, m, turns)
    print("\nReminder: production worker colocated near providers will shave more off every hop.")
    return 0
