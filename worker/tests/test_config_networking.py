from sam_worker.config import Settings, rainmaker_api_base_url


def test_rainmaker_api_base_url_prefers_render_private_host(monkeypatch):
    monkeypatch.setenv("RM_API_BASE_URL", "http://override:9000")
    monkeypatch.setenv("RM_API_HOSTPORT", "rainmaker-api-abcd:10000")

    assert rainmaker_api_base_url() == "http://rainmaker-api-abcd:10000"


def test_rainmaker_api_base_url_uses_render_private_host(monkeypatch):
    monkeypatch.delenv("RM_API_BASE_URL", raising=False)
    monkeypatch.setenv("RM_API_HOSTPORT", "rainmaker-api-abcd:10000")

    assert rainmaker_api_base_url() == "http://rainmaker-api-abcd:10000"


def test_rainmaker_api_base_url_uses_explicit_override_without_private_host(monkeypatch):
    monkeypatch.setenv("RM_API_BASE_URL", "http://override:9000")
    monkeypatch.delenv("RM_API_HOSTPORT", raising=False)

    assert rainmaker_api_base_url() == "http://override:9000"


def test_rainmaker_api_base_url_keeps_public_fallback(monkeypatch):
    monkeypatch.delenv("RM_API_BASE_URL", raising=False)
    monkeypatch.delenv("RM_API_HOSTPORT", raising=False)

    assert rainmaker_api_base_url() == "https://rainmaker-api-waqs.onrender.com"


def test_llm_completion_budget_is_clamped(monkeypatch):
    monkeypatch.setenv("SAM_LLM_MAX_COMPLETION_TOKENS", "10")
    assert Settings.from_env().llm_max_completion_tokens == 64
    monkeypatch.setenv("SAM_LLM_MAX_COMPLETION_TOKENS", "5000")
    assert Settings.from_env().llm_max_completion_tokens == 1024


def test_llm_completion_budget_defaults_to_calendar_safe_limit(monkeypatch):
    monkeypatch.delenv("SAM_LLM_MAX_COMPLETION_TOKENS", raising=False)
    assert Settings.from_env().llm_max_completion_tokens == 512
