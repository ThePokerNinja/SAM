from __future__ import annotations

from sam_worker.config import Settings
from sam_worker.gpt_live_lab import (
    LIVE_INSTRUCTIONS,
    build_gpt_live_model,
    gpt_live_lab_enabled,
)


def test_gpt_live_disabled_by_default() -> None:
    s = Settings(openai_api_key="sk-test")
    assert gpt_live_lab_enabled(s, "staging-demo") is False


def test_gpt_live_requires_staging_room() -> None:
    s = Settings(voice_arch="gpt-live", openai_api_key="sk-test")
    assert gpt_live_lab_enabled(s, "voice-portal-abc") is False
    assert gpt_live_lab_enabled(s, "staging-human-voice") is True
    assert gpt_live_lab_enabled(s, "sam-gptlive-lab1") is True


def test_gpt_live_requires_openai_key() -> None:
    s = Settings(voice_arch="gpt-live")
    assert gpt_live_lab_enabled(s, "staging-test") is False


def test_build_gpt_live_model_custom_voice(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = Settings(
        voice_arch="gpt-live",
        openai_api_key="sk-test",
        openai_custom_voice_id="voice_abc123",
    )
    model = build_gpt_live_model(s)
    assert model.model == "gpt-live-1"


def test_live_instructions_are_short() -> None:
    assert len(LIVE_INSTRUCTIONS) < 2000
    assert "Hermes" in LIVE_INSTRUCTIONS
