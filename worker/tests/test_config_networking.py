from sam_worker.config import rainmaker_api_base_url


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
