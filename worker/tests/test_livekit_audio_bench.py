from __future__ import annotations

import json
import struct
import wave

from sam_worker.bench.livekit_audio import (
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
