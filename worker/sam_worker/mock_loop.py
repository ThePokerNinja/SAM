"""Stdlib-only simulated turn loop for `python -m sam_worker --mock`.

No LiveKit / Deepgram / ElevenLabs / network needed. Exercises the brain interface, the tier
state, and the Rainmaker tool client, printing a per-stage latency breakdown so the loop is
reviewable offline. Mirrors the client's MockTransport timings."""

from __future__ import annotations

import asyncio
import random
import time

from .brain import MockBrain
from .personas import SAMUEL, SUB_AGENTS
from .tier import TierState
from .tools.rainmaker import MockRainmakerClient

_PROMPTS = [
    "Sam, what's the morning read?",
    "How's NVDA setting up?",
    "Give me the team brief.",
    "Any blockers from design?",
    "What's sales pipeline looking like?",
]


async def _simulate_turn(brain: MockBrain, tier: TierState, persona, prompt: str) -> float:
    t0 = time.perf_counter()
    turn_detect = random.uniform(0.18, 0.32)
    stt = random.uniform(0.04, 0.14)
    await asyncio.sleep(turn_detect + stt)

    # brain streaming - v2v is time to FIRST token (TTS starts on the first sentence;
    # the rest of the stream plays during "speaking" and does not count against v2v).
    first_token_at = None
    async for _tok in brain.stream(prompt, model=tier.model, history=[]):
        first_token_at = time.perf_counter()
        break
    brain_ttft = (first_token_at - t0 - turn_detect - stt) if first_token_at else 0.0

    tts_ttfb = random.uniform(0.09, 0.19)
    net = random.uniform(0.025, 0.08)
    await asyncio.sleep(tts_ttfb + net)
    v2v = (time.perf_counter() - t0) * 1000

    print(
        f"  [{persona.display_name:<14}] model={tier.model:<12} "
        f"detect={turn_detect*1000:5.0f}ms stt={stt*1000:4.0f}ms "
        f"brain_ttft={brain_ttft*1000:5.0f}ms tts={tts_ttfb*1000:4.0f}ms "
        f"net={net*1000:3.0f}ms  v2v={v2v:6.0f}ms "
        f"{'OK' if v2v <= 800 else 'SLOW'}"
    )
    return v2v


async def run_mock(turns: int = 6) -> None:
    brain = MockBrain()
    rm = MockRainmakerClient()
    tier = TierState(tier=2)

    print("S.A.M. worker - MOCK loop (no external services)")
    print(f"Persona host: {SAMUEL.display_name}; sub-agents: "
          f"{', '.join(p.display_name for p in SUB_AGENTS)}")
    pulse = await rm.get_pulse()
    print(f"Rainmaker pulse (mock): regime={pulse['regime']} breadth={pulse['breadth']}\n")

    personas = [SAMUEL, *SUB_AGENTS]
    v2vs: list[float] = []
    for i in range(turns):
        # simulate a degradation partway through to show per-tier model swap
        if i == turns // 2:
            tier.update(3)
            print(f"  -- tier downgrade -> {tier.tier} (model now {tier.model}) --")
        persona = personas[i % len(personas)]
        prompt = _PROMPTS[i % len(_PROMPTS)]
        v2vs.append(await _simulate_turn(brain, tier, persona, prompt))

    v2vs.sort()
    p50 = v2vs[len(v2vs) // 2]
    p95 = v2vs[min(len(v2vs) - 1, int(0.95 * len(v2vs)))]
    print(f"\nSummary: {turns} turns  v2v p50={p50:.0f}ms  p95={p95:.0f}ms  "
          f"(KPI: p50<=800, p95<=1500)")
