from __future__ import annotations

from types import SimpleNamespace

from livekit.agents import APIStatusError

from sam_worker import agent
from sam_worker.config import Settings


def test_recovery_utterance_distinguishes_rate_limit_from_generic() -> None:
    rate_limit = SimpleNamespace(
        error=SimpleNamespace(error=APIStatusError("busy", status_code=429))
    )
    assert agent._error_status(rate_limit) == 429
    assert "catching up" in agent._recovery_utterance(rate_limit)
    assert "Say it again" in agent._recovery_utterance(RuntimeError("offline"))


def test_barge_overlap_uses_event_timestamps_and_captures_agent_stop() -> None:
    state = {"t0_ms": None, "measured_ms": None}
    user_started = SimpleNamespace(new_state="speaking", created_at=100.000)
    agent._start_barge_overlap(state, user_started, other_state="speaking")
    assert state["t0_ms"] == 100_000.0

    agent_stopped = SimpleNamespace(
        old_state="speaking",
        new_state="listening",
        created_at=100.120,
    )
    measured = agent._finish_barge_overlap(state, agent_stopped)
    assert measured is not None
    assert round(measured) == 120
    assert state["t0_ms"] is None
    assert round(float(state["measured_ms"])) == 120


def test_groq_fallback_chain_builds_configured_rungs(monkeypatch) -> None:
    built: list[tuple[str, str, str]] = []
    captured: dict[str, object] = {}

    def fake_llm(*, model, base_url, api_key, **_kwargs):
        built.append((model, base_url, api_key))
        return SimpleNamespace(model=model)

    def fake_fallback(*, llm, attempt_timeout, max_retry_per_llm):
        captured.update(
            llm=llm,
            attempt_timeout=attempt_timeout,
            max_retry_per_llm=max_retry_per_llm,
        )
        return "fallback"

    monkeypatch.setattr(agent.openai, "LLM", fake_llm)
    monkeypatch.setattr(agent.llm, "FallbackAdapter", fake_fallback)
    settings = Settings(
        groq_api_key="groq-key",
        groq_model="primary",
        groq_fallback_model="secondary",
        cerebras_api_key="cerebras-key",
        cerebras_model="last",
    )
    assert agent._build_llm(settings) == "fallback"
    assert [row[0] for row in built] == ["primary", "secondary", "last"]
    assert captured["attempt_timeout"] == 1.5
    assert captured["max_retry_per_llm"] == 0


def test_missing_groq_credentials_keeps_openai_path(monkeypatch) -> None:
    monkeypatch.setattr(agent.openai, "LLM", lambda **kwargs: kwargs)
    settings = Settings(openai_api_key="openai-key", openai_model="control")
    result = agent._build_llm(settings)
    assert result["model"] == "control"
    assert result["api_key"] == "openai-key"
