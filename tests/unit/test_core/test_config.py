from medcheck.core.config import Settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("MEDCHECK_HOST", raising=False)
    monkeypatch.delenv("MEDCHECK_MAX_VISION_IMAGES", raising=False)
    monkeypatch.delenv("MEDCHECK_MAX_DOWNLOAD_BYTES", raising=False)
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.default_llm_provider == "claude"
    assert settings.default_language == "en"
    assert settings.api_key is None
    assert settings.max_vision_images == 12
    assert settings.max_download_bytes == 2 * 1024 * 1024 * 1024


def test_resource_limit_settings_from_env(monkeypatch):
    monkeypatch.setenv("MEDCHECK_MAX_VISION_IMAGES", "4")
    monkeypatch.setenv("MEDCHECK_MAX_DOWNLOAD_BYTES", "1048576")
    settings = Settings()
    assert settings.max_vision_images == 4
    assert settings.max_download_bytes == 1048576


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MEDCHECK_PORT", "9090")
    monkeypatch.setenv("MEDCHECK_LLM_PROVIDER", "gemini")
    settings = Settings()
    assert settings.port == 9090
    assert settings.default_llm_provider == "gemini"


def test_settings_api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    settings = Settings()
    assert settings.anthropic_api_key == "sk-test-123"
    assert settings.openai_api_key is None


def test_available_providers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("GOOGLE_API_KEY", "gk-test")
    settings = Settings()
    providers = settings.available_llm_providers()
    assert "claude" in providers
    assert "gemini" in providers
    assert "openai" not in providers
    assert "local" in providers
