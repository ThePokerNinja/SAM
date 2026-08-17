from __future__ import annotations

from livekit.plugins import deepgram

from sam_worker.config import Settings
from sam_worker.stt import build_stt


def test_direct_nova_uses_v1_plugin() -> None:
    stt = build_stt(Settings(deepgram_api_key="test", stt_model="deepgram/nova-3"))
    assert type(stt) is deepgram.STT


def test_flux_uses_v2_plugin_and_native_eot_timeout() -> None:
    stt = build_stt(
        Settings(
            deepgram_api_key="test",
            stt_model="deepgram/flux-general-en",
            stt_eot_timeout_ms=650,
        )
    )
    assert type(stt) is deepgram.STTv2
    assert stt._opts.eot_timeout_ms == 650


def test_flux_timeout_is_clamped_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SAM_STT_EOT_TIMEOUT_MS", "100")
    assert Settings.from_env().stt_eot_timeout_ms == 500

    monkeypatch.setenv("SAM_STT_EOT_TIMEOUT_MS", "70000")
    assert Settings.from_env().stt_eot_timeout_ms == 60_000
