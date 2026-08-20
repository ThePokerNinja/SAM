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


def test_fallback_and_prompt_cache_config(monkeypatch):
    monkeypatch.setenv("GROQ_FALLBACK_MODEL", "fallback-model")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")
    monkeypatch.setenv("CEREBRAS_BASE_URL", "https://cerebras.test/v1")
    monkeypatch.setenv("CEREBRAS_MODEL", "last-resort")
    monkeypatch.setenv("SAM_PROMPT_TOOL_MODE", "stable_full")
    monkeypatch.setenv("GROQ_TPM_BUDGET", "12000")
    settings = Settings.from_env()
    assert settings.groq_fallback_model == "fallback-model"
    assert settings.cerebras_api_key == "cerebras-key"
    assert settings.cerebras_base_url == "https://cerebras.test/v1"
    assert settings.cerebras_model == "last-resort"
    assert settings.prompt_tool_mode == "stable_full"
    assert settings.groq_tpm_budget == 12000


def test_dynamic_tools_remain_default(monkeypatch):
    monkeypatch.delenv("SAM_PROMPT_TOOL_MODE", raising=False)
    assert Settings.from_env().prompt_tool_mode == "dynamic"


def test_groq_fallback_defaults_to_oss_120b(monkeypatch):
    monkeypatch.delenv("GROQ_FALLBACK_MODEL", raising=False)
    assert Settings.from_env().groq_fallback_model == "openai/gpt-oss-120b"
