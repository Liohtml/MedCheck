from typer.testing import CliRunner

from medcheck.main import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


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
