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


def test_download_models_reports_missing_torch(monkeypatch):
    from unittest.mock import patch as mock_patch

    with mock_patch(
        "medcheck.pipeline.ml_analysis._build_feature_extractor",
        side_effect=ImportError("No module named 'torch'"),
    ):
        result = runner.invoke(app, ["download-models"])
    assert result.exit_code == 1
    assert "PyTorch is not installed" in result.output


def test_download_models_caches_weights():
    from unittest.mock import patch as mock_patch

    with mock_patch("medcheck.pipeline.ml_analysis._build_feature_extractor", return_value=object()) as build:
        result = runner.invoke(app, ["download-models"])
    assert result.exit_code == 0
    build.assert_called_once()
    assert "cached" in result.output


def test_analyze_study_privacy_reference_and_export_flags(monkeypatch, tmp_path):
    reference = tmp_path / "reference.txt"
    reference.write_text("ACL unauffällig — Referenzbefund", encoding="utf-8")
    captured = {}

    def run_pipeline(ctx, workflow, steps):
        captured.update(ctx=ctx, steps=steps)
        return ctx

    with patch("medcheck.main._run_pipeline", side_effect=run_pipeline):
        result = runner.invoke(
            app,
            [
                "analyze",
                str(tmp_path),
                "--study-uid",
                "1.2.3.4",
                "--pixels-reviewed",
                "--deidentify",
                "--allow-cloud-llm",
                "--model",
                "claude",
                "--official-report",
                str(reference),
                "--report",
                "fhir",
                "--ocr-redact",
                "--output",
                str(tmp_path / "output"),
            ],
        )
    assert result.exit_code == 0, result.output
    ctx = captured["ctx"]
    assert ctx.study_instance_uid == "1.2.3.4"
    assert ctx.pixels_reviewed and ctx.allow_external_llm and ctx.deidentify
    assert ctx.official_report == "ACL unauffällig — Referenzbefund"
    assert ctx.report_format == "fhir"
    assert ctx.analysis_provenance["ocr_requested"] is True
    assert captured["steps"].split(",") == [
        "ingest",
        "preprocess",
        "ml_analysis",
        "vision_analysis",
        "reconcile",
        "report",
    ]


def test_analyze_dicom_sr_and_default_pixel_review_not_assumed(monkeypatch, tmp_path):
    result, ctx = _capture_analyze_context(
        monkeypatch,
        [
            "analyze",
            str(tmp_path),
            "--report",
            "dicom-sr",
            "--output",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 0
    assert ctx.report_format == "dicom-sr"
    assert ctx.pixels_reviewed is False
    assert ctx.analysis_provenance["ocr_requested"] is False


def test_evaluate_cli_writes_artifact_and_fails_on_regression(tmp_path):
    import json

    report = tmp_path / "report.json"
    report.write_text(json.dumps({"findings": [{"name": "ACL", "status": "normal"}]}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "case-1",
                    "report": "report.json",
                    "expected": [{"name": "ACL", "status": "normal"}],
                }
            ]
        )
    )
    baseline = tmp_path / "baseline.json"
    result = runner.invoke(app, ["evaluate", str(manifest), "--output", str(baseline)])
    assert result.exit_code == 0, result.output
    assert json.loads(baseline.read_text())["aggregate"]["true_positives"] == 1
    report.write_text(json.dumps({"findings": []}))
    output = tmp_path / "regression.json"
    result = runner.invoke(app, ["evaluate", str(manifest), "--baseline", str(baseline), "--output", str(output)])
    assert result.exit_code == 1
    assert json.loads(output.read_text())["passed"] is False


def test_evaluate_cli_invalid_manifest_does_not_create_output(tmp_path):
    manifest = tmp_path / "invalid.json"
    manifest.write_text("{}")
    output = tmp_path / "out.json"
    result = runner.invoke(app, ["evaluate", str(manifest), "--output", str(output)])
    assert result.exit_code == 2
    assert "Manifest must be a JSON array" in result.output
    assert not output.exists()
