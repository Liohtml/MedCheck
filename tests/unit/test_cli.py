from unittest.mock import patch

from typer.testing import CliRunner

from medcheck.main import app

runner = CliRunner()


def _capture_analyze_context(monkeypatch, argv):
    """Run `analyze` with the pipeline stubbed, returning the built context."""
    captured = {}

    def fake_run_pipeline(ctx, workflow, steps):
        captured["ctx"] = ctx
        return ctx

    with patch("medcheck.main._run_pipeline", side_effect=fake_run_pipeline):
        result = runner.invoke(app, argv)
    return result, captured.get("ctx")


def test_analyze_uses_configured_default_provider(monkeypatch, tmp_path):
    # #73: with no --model, MEDCHECK_LLM_PROVIDER must flow into the context.
    monkeypatch.setenv("MEDCHECK_LLM_PROVIDER", "claude")
    result, ctx = _capture_analyze_context(monkeypatch, ["analyze", str(tmp_path)])
    assert result.exit_code == 0
    assert ctx is not None
    assert ctx.llm_provider == "claude"


def test_analyze_model_flag_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDCHECK_LLM_PROVIDER", "claude")
    result, ctx = _capture_analyze_context(monkeypatch, ["analyze", str(tmp_path), "--model", "gemini"])
    assert result.exit_code == 0
    assert ctx.llm_provider == "gemini"


def test_analyze_rejects_invalid_report_format(monkeypatch, tmp_path):
    # #99: an unknown --report value must fail fast, not silently fall back to JSON.
    result, ctx = _capture_analyze_context(monkeypatch, ["analyze", str(tmp_path), "--report", "xml"])
    assert result.exit_code != 0
    assert ctx is None


def test_analyze_rejects_invalid_language(monkeypatch, tmp_path):
    # #99: an unsupported --lang value must fail fast with a clear error.
    result, ctx = _capture_analyze_context(monkeypatch, ["analyze", str(tmp_path), "--lang", "klingon"])
    assert result.exit_code != 0
    assert ctx is None


def test_serve_honors_host_port_env(monkeypatch):
    # #105: Docker sets MEDCHECK_HOST/PORT; `serve` (no flags) must bind to them
    # instead of the hardcoded 127.0.0.1:8080, or the container is unreachable.
    monkeypatch.setenv("MEDCHECK_HOST", "0.0.0.0")
    monkeypatch.setenv("MEDCHECK_PORT", "9000")
    monkeypatch.setenv("MEDCHECK_API_KEY", "k")  # silence the open-bind warning path
    captured = {}

    def fake_run(_app_obj, host, port):
        # Signature mirrors uvicorn.run(app, host=, port=); we only assert host/port.
        captured["host"] = host
        captured["port"] = port

    with patch("uvicorn.run", side_effect=fake_run):
        result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    assert captured == {"host": "0.0.0.0", "port": 9000}


def test_cli_version():
    from medcheck import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "serve" in result.stdout


def test_cli_providers():
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "local" in result.stdout
    assert "easyradiology" in result.stdout


def test_cli_models():
    result = runner.invoke(app, ["models"])
    assert result.exit_code == 0
    assert "claude" in result.stdout
    assert "openai" in result.stdout
    assert "gemini" in result.stdout
