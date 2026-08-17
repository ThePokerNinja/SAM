"""Run deterministic speech fixtures through a real LiveKit room."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import AgentSession, MetricsCollectedEvent, function_tool, metrics
from livekit.agents.utils import http_context
from livekit.plugins import elevenlabs, silero

from ..agent import _build_llm
from ..config import Settings
from ..prompt_budget import samuel_instructions
from ..router import FastIntentRouter, RoutedSamuelAgent
from ..stt import build_stt
from ..tool_latency import ToolLatencyManager
from ..tools.handlers import build_rainmaker_client
from ..tools.rainmaker_registry import register_rainmaker_tools
from ..tools.registry import ToolRegistry
from ..turns import build_turn_handling
from .evaluation import TaskObservation, evaluate_observations
from .fixtures import GROUNDED_TASKS
from .latency_profile import analyze, analyze_eou_drift
from .livekit_audio import LiveKitAudioDriver, load_manifest, mint_token


async def _start_embedded_agent(
    *,
    url: str,
    api_key: str,
    api_secret: str,
    room_name: str,
    turn_mode: str,
    interruption_mode: str,
    sam_brain: str = "",
    llm_model: str = "",
    endpoint_min: float | None = None,
    endpoint_max: float | None = None,
) -> tuple[rtc.Room, AgentSession]:
    settings = Settings.from_env()
    updates: dict[str, object] = {
        "turn_mode": turn_mode,
        "interruption_mode": interruption_mode,
    }
    if sam_brain:
        updates["sam_brain"] = sam_brain
    if llm_model:
        if (sam_brain or settings.sam_brain) in {"groq", "hybrid"}:
            updates["groq_model"] = llm_model
        else:
            updates["openai_model"] = llm_model
    if endpoint_min is not None:
        updates["endpoint_min"] = endpoint_min
    if endpoint_max is not None:
        updates["endpoint_max"] = endpoint_max
    updates["sam_mock_rm"] = True
    settings = replace(settings, **updates)
    token = mint_token(
        api_key,
        api_secret,
        room=room_name,
        identity=f"embedded-agent-{uuid.uuid4().hex[:8]}",
    )
    room = rtc.Room()
    await room.connect(url, token)
    session = AgentSession(
        stt=build_stt(settings),
        llm=_build_llm(settings),
        tts=elevenlabs.TTS(
            model=settings.elevenlabs_model,
            voice_id=settings.voice_ids["samuel"],
            api_key=settings.elevenlabs_api_key,
        ),
        vad=silero.VAD.load(),
        turn_handling=build_turn_handling(settings),
    )
    registry = ToolRegistry()
    register_rainmaker_tools(registry)
    tools = registry.build_livekit_tools(
        build_rainmaker_client(settings),
        lambda: True,
        function_tool=function_tool,
        owner_refusal="Owner only.",
        deps={"tool_latency_manager": ToolLatencyManager()},
    )
    router = FastIntentRouter()

    async def _direct(decision):
        return await router.execute(decision, rainmaker_client=build_rainmaker_client(settings))

    async def _publish_command(_command: dict) -> None:
        return None

    async def _publish_bench(payload: dict) -> None:
        try:
            await room.local_participant.publish_data(
                json.dumps(payload),
                reliable=True,
                topic="sam-bench",
            )
        except Exception:  # noqa: BLE001
            return

    @session.on("conversation_item_added")
    def _bench_message(ev) -> None:
        item = getattr(ev, "item", None)
        if getattr(item, "role", None) != "assistant":
            return
        text = str(getattr(item, "text_content", "") or "").strip()
        if text:
            asyncio.ensure_future(_publish_bench({"type": "assistant_message", "text": text}))

    eou_rows: list[dict] = []
    turn_index = {"n": 0}

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        collected = ev.metrics
        if isinstance(collected, metrics.EOUMetrics):
            turn_index["n"] += 1
            eou_rows.append(
                {
                    "turn_index": turn_index["n"],
                    "eou_ms": collected.end_of_utterance_delay * 1000.0,
                    "transcription_delay_ms": (
                        collected.transcription_delay * 1000.0
                        if getattr(collected, "transcription_delay", None) is not None
                        else None
                    ),
                }
            )
        elif isinstance(collected, metrics.LLMMetrics):
            if eou_rows:
                eou_rows[-1]["prompt_tokens"] = getattr(collected, "prompt_tokens", None)
                eou_rows[-1]["llm_ttft_ms"] = collected.ttft * 1000.0

    @session.on("function_tools_executed")
    def _bench_tools(ev) -> None:
        names = [
            str(getattr(call, "name", "") or "")
            for call in (getattr(ev, "function_calls", None) or [])
            if getattr(call, "name", None)
        ]
        if names:
            asyncio.ensure_future(_publish_bench({"type": "tool_calls", "names": names}))

    await session.start(
        agent=RoutedSamuelAgent(
            router=router,
            direct_execute=_direct,
            publish_command=_publish_command,
            publish_bench=_publish_bench,
            history_token_cap=settings.history_token_cap,
            instructions=samuel_instructions(
                extra=(
                    "Answer each benchmark prompt directly, accurately, and briefly. "
                    "For a request for a long explanation, continue speaking until interrupted."
                )
            ),
            tools=tools,
        ),
        room=room,
    )
    return room, session, eou_rows


async def _run(args) -> dict:
    load_dotenv()
    url = os.getenv("LIVEKIT_URL", "").strip()
    api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    if not all((url, api_key, api_secret)):
        raise RuntimeError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are required")

    prefix = "sam-wave8-embedded" if args.embedded_agent else "sam-wave8"
    room_name = args.room or f"{prefix}-{uuid.uuid4().hex[:12]}"
    token = mint_token(api_key, api_secret, room=room_name, identity=f"bench-{uuid.uuid4().hex[:8]}")
    fixtures = load_manifest(args.manifest)
    turns = [fixture for fixture in fixtures if fixture.kind in {"short", "long"}]
    if args.max_turns is not None:
        turns = turns[: max(0, args.max_turns)]
    prompt = next((fixture for fixture in fixtures if fixture.kind == "barge_prompt"), None)
    interruption = next((fixture for fixture in fixtures if fixture.kind == "interruption"), None)
    decoys = [fixture for fixture in fixtures if fixture.kind == "decoy"]

    driver = LiveKitAudioDriver(
        url=url,
        token=token,
        participant_identity_prefix="embedded-agent-" if args.embedded_agent else "",
        debug_audio_path=(
            args.output.with_suffix(".audio.jsonl") if args.debug_audio else None
        ),
    )
    if args.agent_name:
        livekit_api = api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)
        try:
            await livekit_api.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(agent_name=args.agent_name, room=room_name)
            )
        finally:
            await livekit_api.aclose()
    embedded_room: rtc.Room | None = None
    embedded_session: AgentSession | None = None
    eou_rows: list[dict] = []
    results = []
    try:
        if args.embedded_agent:
            embedded_room, embedded_session, eou_rows = await _start_embedded_agent(
                url=url,
                api_key=api_key,
                api_secret=api_secret,
                room_name=room_name,
                turn_mode=args.turn_mode,
                interruption_mode=args.interruption_mode,
                sam_brain=args.sam_brain,
                llm_model=args.llm_model,
                endpoint_min=args.endpoint_min,
                endpoint_max=args.endpoint_max,
            )
        await driver.connect()
        await driver.wait_ready(timeout_s=args.agent_timeout)
        await driver.wait_initial_greeting()
        for fixture in turns:
            results.append(
                await driver.measure_turn(
                    fixture,
                    turn_mode=args.turn_mode,
                    timeout_s=args.turn_timeout,
                )
            )
        if not args.skip_barge and prompt is not None and interruption is not None:
            results.append(
                await driver.measure_barge_in(
                    prompt=prompt,
                    interruption=interruption,
                    turn_mode=args.turn_mode,
                )
            )
            for decoy in decoys:
                results.append(
                    await driver.measure_decoy(
                        prompt=prompt,
                        decoy=decoy,
                        turn_mode=args.turn_mode,
                    )
                )
    finally:
        await driver.close()
        if embedded_session is not None:
            await embedded_session.aclose()
        if embedded_room is not None:
            await embedded_room.disconnect()

    rows = [result.to_dict() for result in results]
    profile_rows = [
        {
            "speech_id": row["fixture_id"],
            "turn_mode": row["turn_mode"],
            "v2v_ms": row["v2v_ms"],
            "barge_in_ms": row["barge_in_ms"],
        }
        for row in rows
        if row["v2v_ms"] is not None and row["kind"] in {"short", "long"}
    ]
    cutoffs = [row for row in rows if row["kind"] in {"short", "long"}]
    expected = {fixture.id: fixture for fixture in GROUNDED_TASKS}
    observations = []
    for row in rows:
        fixture = expected.get(row["fixture_id"])
        if fixture is None:
            continue
        calls = list(row.get("tool_calls") or [])
        actual_tool = calls[0] if calls else None
        response = str(row.get("assistant_text") or "")
        has_unverified_number = bool(re.search(r"[$]\s*\d|\b\d+[.]\d{2}\b", response))
        tool_correct = actual_tool == fixture.expected_tool
        refusal_ok = (
            fixture.expected_tool is not None
            or (
                not has_unverified_number
                and any(
                    phrase in response.lower()
                    for phrase in ("can't verify", "cannot verify", "not configured", "don't have")
                )
            )
        )
        observations.append(
            TaskObservation(
                fixture_id=fixture.id,
                response=response,
                tool_called=actual_tool,
                task_succeeded=bool(response) and tool_correct and refusal_ok,
                hallucinated=has_unverified_number and not tool_correct,
                refusal_appropriate=refusal_ok,
                intent_correct=tool_correct,
                context_retained=bool(response),
            )
        )
    barge_rows = [row for row in rows if row["kind"] == "barge_in"]
    barge_pass = [
        row
        for row in barge_rows
        if row.get("barge_in_ms") is not None and row["barge_in_ms"] < 250
    ]
    decoy_rows = [row for row in rows if row["kind"] == "decoy"]
    false_positives = sum(1 for row in decoy_rows if row.get("false_trigger"))
    true_positives = len(barge_pass)
    false_negatives = len(barge_rows) - true_positives
    f1_denominator = 2 * true_positives + false_positives + false_negatives
    barge_f1 = (2 * true_positives / f1_denominator) if f1_denominator else 0.0
    total_interruptions = len(barge_rows) + len(decoy_rows)
    interruption_accuracy = (
        (true_positives + len(decoy_rows) - false_positives) / total_interruptions
        if total_interruptions
        else 0.0
    )
    intelligence = evaluate_observations(
        observations,
        v2v_ms=[row["v2v_ms"] for row in profile_rows if row["v2v_ms"] is not None],
        barge_in_f1=barge_f1,
        interruption_accuracy=interruption_accuracy,
        arm=args.arm or "samuel",
    )
    return {
        "method": "livekit_external_audio_v1",
        "room": room_name,
        "turn_mode": args.turn_mode,
        "interruption_mode": args.interruption_mode,
        "sam_brain": args.sam_brain or None,
        "llm_model": args.llm_model or None,
        "endpoint_min": args.endpoint_min,
        "endpoint_max": args.endpoint_max,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": rows,
        "cut_off_rate": (
            sum(1 for row in cutoffs if row["cut_off"]) / len(cutoffs) if cutoffs else None
        ),
        "analysis": analyze(profile_rows),
        "interruption": {
            "barge_in_p95_ms": (
                max(row["barge_in_ms"] for row in barge_rows if row["barge_in_ms"] is not None)
                if any(row["barge_in_ms"] is not None for row in barge_rows)
                else None
            ),
            "false_trigger_rate": (
                false_positives / len(decoy_rows) if decoy_rows else None
            ),
            "f1": barge_f1,
        },
        "intelligence": intelligence.summary(),
        "eou_drift": analyze_eou_drift(eou_rows),
        "eou_rows": eou_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Samuel through LiveKit audio")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--turn-mode", choices=["cloud", "mini", "vad", "stt"], required=True)
    parser.add_argument(
        "--interruption-mode",
        choices=["adaptive", "vad"],
        default="adaptive",
    )
    parser.add_argument("--room", default="")
    parser.add_argument("--embedded-agent", action="store_true")
    parser.add_argument(
        "--agent-name",
        default="",
        help="Explicitly dispatch a named LiveKit agent (useful for isolated worker validation)",
    )
    parser.add_argument("--agent-timeout", type=float, default=45.0)
    parser.add_argument("--turn-timeout", type=float, default=15.0)
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--skip-barge", action="store_true")
    parser.add_argument("--sam-brain", default="", help="openai | groq | hybrid")
    parser.add_argument("--llm-model", default="", help="Override OPENAI_MODEL or GROQ_MODEL")
    parser.add_argument("--endpoint-min", type=float)
    parser.add_argument("--endpoint-max", type=float)
    parser.add_argument("--arm", default="", help="Scorecard arm label")
    parser.add_argument(
        "--debug-audio",
        action="store_true",
        help="Write per-frame RMS values and audio state transitions beside --output",
    )
    args = parser.parse_args()

    async def run_with_http_context() -> dict:
        async with http_context.open():
            return await _run(args)

    payload = asyncio.run(run_with_http_context())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["analysis"]["classification"], sort_keys=True))
    return 0 if not any(row["error"] for row in payload["results"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
