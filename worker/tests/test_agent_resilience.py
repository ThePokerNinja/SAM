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
    assert agent._recovery_utterance(rate_limit) == "Give me one moment."
    assert agent._recovery_utterance(RuntimeError("offline")) == "One sec."
    assert (
        agent._recovery_utterance(
            RuntimeError("attempted to call tool 'propose_calendar_change' which was not in request.tools")
        )
        is None
    )


def test_error_status_reads_429_from_message_without_status_code() -> None:
    wrapped = RuntimeError(
        "LLMError: Error code: 429 - Rate limit reached for model "
        "openai/gpt-oss-20b in organization org_test Limit 8000, Used 7700 "
        "Requested 400. Please try again in 6s. Visit https://groq.com "
        "(Request ID: abc) code: rate_limit_exceeded"
    )
    assert agent._error_status(wrapped) == 429
    assert agent._recovery_utterance(wrapped) == "Give me one moment."


def test_error_status_reads_rate_limit_body_code() -> None:
    nested = SimpleNamespace(
        status_code=None,
        body={"error": {"code": "rate_limit_exceeded", "message": "busy"}},
    )
    assert agent._error_status(SimpleNamespace(error=nested)) == 429


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
    )
    assert agent._build_llm(settings) == "fallback"
    assert [row[0] for row in built] == ["primary", "secondary"]
    assert captured["attempt_timeout"] == 2.5
    assert captured["max_retry_per_llm"] == 2


def test_default_groq_fallback_adds_openai_as_independent_rung(monkeypatch) -> None:
    built: list[tuple[str, str, str]] = []

    def fake_llm(*, model, base_url, api_key, **_kwargs):
        built.append((model, base_url, api_key))
        return SimpleNamespace(model=model)

    monkeypatch.setattr(agent.openai, "LLM", fake_llm)
    monkeypatch.setattr(
        agent.llm,
        "FallbackAdapter",
        lambda **kwargs: SimpleNamespace(rungs=kwargs["llm"]),
    )
    settings = Settings(
        groq_api_key="groq-key",
        groq_model="openai/gpt-oss-20b",
        groq_fallback_model="",
        openai_api_key="openai-key",
        openai_model="gpt-4o-mini",
    )
    result = agent._build_llm(settings)
    assert [row[0] for row in built] == [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "gpt-4o-mini",
    ]
    assert built[0][2] == "groq-key"
    assert built[1][2] == "groq-key"
    assert built[2][2] == "openai-key"
    assert len(result.rungs) == 3


def test_single_groq_model_skips_adapter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_llm(*, model, **_kwargs):
        return SimpleNamespace(model=model)

    def fake_fallback(**kwargs):
        captured.update(kwargs)
        return "fallback"

    monkeypatch.setattr(agent.openai, "LLM", fake_llm)
    monkeypatch.setattr(agent.llm, "FallbackAdapter", fake_fallback)
    settings = Settings(
        groq_api_key="groq-key",
        groq_model="openai/gpt-oss-120b",
        groq_fallback_model="openai/gpt-oss-120b",
    )
    result = agent._build_llm(settings)
    assert result.model == "openai/gpt-oss-120b"
    assert captured == {}


def test_missing_groq_credentials_keeps_openai_path(monkeypatch) -> None:
    monkeypatch.setattr(agent.openai, "LLM", lambda **kwargs: kwargs)
    settings = Settings(openai_api_key="openai-key", openai_model="control")
    result = agent._build_llm(settings)
    assert result["model"] == "control"
    assert result["api_key"] == "openai-key"
