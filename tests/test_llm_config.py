from engine.llm_config import get_openrouter_config


def test_get_openrouter_config_defaults(monkeypatch) -> None:
    monkeypatch.setattr("engine.llm_config.read_env_file", lambda: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_APP_NAME", raising=False)
    monkeypatch.delenv("OPENROUTER_SITE_URL", raising=False)

    config = get_openrouter_config()

    assert config.enabled is False
    assert config.model == "openrouter/free"
    assert config.base_url == "https://openrouter.ai/api/v1"
    assert config.app_name == "HAX-Mind"
    assert config.site_url == ""


def test_get_openrouter_config_reads_env(monkeypatch) -> None:
    monkeypatch.setattr("engine.llm_config.read_env_file", lambda: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick:free")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "CustomApp")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")

    config = get_openrouter_config()

    assert config.enabled is True
    assert config.api_key_present is True
    assert config.model == "meta-llama/llama-4-maverick:free"
    assert config.app_name == "CustomApp"
    assert config.site_url == "https://example.com"
