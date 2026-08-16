from __future__ import annotations

import asyncio
import json
import struct
import time
import wave

from sam_worker.bench.livekit_audio import (
    AudioFixture,
    LiveKitAudioDriver,
    load_manifest,
    mint_token,
    pcm_rms,
    read_pcm_frames,
)


def test_pcm_fixture_reader_chunks_20ms(tmp_path) -> None:
    path = tmp_path / "fixture.wav"
    samples = [1000] * 640  # 40ms at 16kHz
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    rate, frames = read_pcm_frames(path)
    assert rate == 16000
    assert len(frames) == 2
    assert pcm_rms(frames[0]) == 1000.0


def test_manifest_paths_are_relative_to_manifest(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "id": "one",
                        "kind": "short",
                        "file": "one.wav",
                        "transcript": "hello",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fixture = load_manifest(manifest)[0]
    assert fixture.path == (tmp_path / "one.wav").resolve()


def test_benchmark_token_is_room_scoped() -> None:
    token = mint_token(
        "key",
        "secret-value-that-is-at-least-thirty-two-bytes",
        room="bench-room",
        identity="driver",
    )
    assert isinstance(token, str)
    assert token.count(".") == 2


def test_rolling_silence_rearms_after_one_noisy_frame() -> None:
    async def exercise() -> list[str]:
        driver = LiveKitAudioDriver(url="ws://example.invalid", token="test")
        now = time.perf_counter()
        await driver._process_audio_level(True, now)
        for index in range(40):
            await driver._process_audio_level(index == 20, now + (index + 1) * 0.02)
        await driver._process_audio_level(True, now + 1.0)
        events = []
        while not driver.events.empty():
            kind, _timestamp = driver.events.get_nowait()
            events.append(kind)
        return events

    assert asyncio.run(exercise()) == [
        "audio_started",
        "audio_paused",
        "audio_stopped",
        "audio_started",
    ]


def test_timeout_preserves_agent_events(tmp_path) -> None:
    async def exercise():
        driver = LiveKitAudioDriver(url="ws://example.invalid", token="test")
        fixture = AudioFixture("one", tmp_path / "unused.wav", "short", "hello")

        async def publish(_fixture):
            started = time.perf_counter()
            driver.bench_events.extend(
                [
                    {"type": "tool_calls", "names": ["get_pulse"]},
                    {"type": "assistant_message", "text": "Market pulse is risk-on."},
                ]
            )
            return started, started

        driver.publish_fixture = publish
        return await driver.measure_turn(fixture, turn_mode="stt", timeout_s=0.01)

    result = asyncio.run(exercise())
    assert result.error == "TimeoutError"
    assert result.heard_audio is False
    assert result.tool_calls == ("get_pulse",)
    assert result.assistant_text == "Market pulse is risk-on."
    assert result.agent_event_types == ("tool_calls", "assistant_message")
