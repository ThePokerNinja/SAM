from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
import wave
from pathlib import Path

import pytest

from sam_worker.bench.livekit_audio import (
    AUDIO_FRAME_MS,
    AUDIO_PAUSE_SILENT_COUNT,
    AUDIO_PAUSED_LAG_S,
    AudioFixture,
    LiveKitAudioDriver,
    PublishTiming,
    compute_barge_in_ms,
    load_manifest,
    mint_token,
    pcm_rms,
    read_pcm_frames,
)
from sam_worker.bench.run_audio_bench import _worker_info_mismatches


def test_worker_info_gate_refuses_missing_or_mismatched_worker() -> None:
    expected = ["turn_mode=stt", "resolved_brain=groq"]
    assert _worker_info_mismatches(None, expected) == ["worker_info was not received"]
    assert _worker_info_mismatches(
        {"turn_mode": "cloud", "resolved_brain": "groq"}, expected
    ) == ["turn_mode expected 'stt', received 'cloud'"]
    assert not _worker_info_mismatches(
        {"turn_mode": "stt", "resolved_brain": "groq"}, expected
    )


def test_owner_benchmark_token_carries_explicit_role() -> None:
    token = mint_token(
        "test-key",
        "test-secret-test-secret-test-secret",
        room="room",
        identity="bench-owner",
        attributes={"role": "owner"},
    )
    encoded_payload = token.split(".")[1]
    payload = json.loads(
        base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
    )
    assert payload["attributes"] == {"role": "owner"}


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

        async def publish(_fixture, reset=True):
            started = time.perf_counter()
            driver.bench_events.extend(
                [
                    {"type": "tool_calls", "names": ["get_pulse"]},
                    {"type": "assistant_message", "text": "Market pulse is risk-on."},
                ]
            )
            return PublishTiming(started, started, started)

        driver.publish_fixture = publish
        return await driver.measure_turn(fixture, turn_mode="stt", timeout_s=0.01)

    result = asyncio.run(exercise())
    assert result.error == "TimeoutError"
    assert result.heard_audio is False
    assert result.tool_calls == ("get_pulse",)
    assert result.assistant_text == "Market pulse is risk-on."
    assert result.agent_event_types == ("tool_calls", "assistant_message")


def test_pause_lag_is_six_silent_frames() -> None:
    assert AUDIO_PAUSED_LAG_S == pytest.approx(
        (AUDIO_PAUSE_SILENT_COUNT - 1) * (AUDIO_FRAME_MS / 1000.0)
    )
    assert compute_barge_in_ms(1.0, 1.4) == 300.0
    assert compute_barge_in_ms(1.0, 1.05) == 0.0


def test_audio_paused_fires_after_known_silent_offset() -> None:
    async def exercise() -> float:
        driver = LiveKitAudioDriver(url="ws://example.invalid", token="test")
        started = time.perf_counter()
        await driver._process_audio_level(True, started)
        frame = AUDIO_FRAME_MS / 1000.0
        for index in range(8):
            await driver._process_audio_level(True, started + (index + 1) * frame)
        silence_start = started + 9 * frame
        paused_at = None
        for index in range(AUDIO_PAUSE_SILENT_COUNT):
            stamp = silence_start + index * frame
            await driver._process_audio_level(False, stamp)
            while not driver.events.empty():
                kind, timestamp = driver.events.get_nowait()
                if kind == "audio_paused":
                    paused_at = timestamp
        assert paused_at is not None
        return round((paused_at - silence_start) * 1000.0, 1)

    lag_ms = asyncio.run(exercise())
    assert lag_ms == pytest.approx(AUDIO_PAUSED_LAG_S * 1000.0, abs=0.1)


def test_measure_barge_in_uses_first_voice_and_subtracts_lag() -> None:
    async def exercise() -> float:
        driver = LiveKitAudioDriver(url="ws://example.invalid", token="test")
        prompt = AudioFixture("prompt", Path("unused.wav"), "barge_prompt", "talk")
        interruption = AudioFixture("stop", Path("unused.wav"), "interruption", "stop")
        first_voice = time.perf_counter() + 0.05

        async def publish(fixture, reset=True):
            if fixture.kind == "barge_prompt":
                now = time.perf_counter()
                await driver.events.put(("audio_started", now + 0.01))
                return PublishTiming(now, now, now)
            await driver.events.put(("audio_paused", first_voice + 0.4))
            return PublishTiming(first_voice, first_voice, first_voice + 0.05)

        driver.publish_fixture = publish
        result = await driver.measure_barge_in(
            prompt=prompt,
            interruption=interruption,
            turn_mode="stt",
        )
        assert result.error is None
        return result.barge_in_ms

    assert asyncio.run(exercise()) == pytest.approx(compute_barge_in_ms(0.0, 0.4), abs=0.1)


def test_interrupt_publish_skips_reset(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    samples = [2000] * 320
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    fixture = AudioFixture("tone", path, "interruption", "stop")

    async def exercise() -> tuple[bool, int]:
        driver = LiveKitAudioDriver(url="ws://example.invalid", token="test")
        await driver._process_audio_level(True, time.perf_counter())
        resets = 0
        original = driver.reset_turn_state

        def spy() -> None:
            nonlocal resets
            resets += 1
            original()

        driver.reset_turn_state = spy
        driver.source.capture_frame = lambda *_args, **_kwargs: asyncio.sleep(0)
        await driver.publish_fixture(fixture, reset=False)
        return driver._speaking, resets

    speaking, resets = asyncio.run(exercise())
    assert speaking is True
    assert resets == 0
