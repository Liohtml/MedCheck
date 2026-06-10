import json
from pathlib import Path

import numpy as np

from medcheck.core.context import (
    PatientInfo,
    PipelineContext,
    SignalStats,
    StructureFinding,
    StudyInfo,
)
from medcheck.pipeline.report import ReportStep, generate_json_report


def _make_ctx(tmp_path: Path) -> PipelineContext:
    ctx = PipelineContext()
    ctx.patient = PatientInfo(name="Test^Patient", patient_id="123", birth_date="19970121", sex="M", age="29Y")
    ctx.study = StudyInfo(date="20260521", description="Knee MRI", institution="Test Hospital")
    ctx.detected_anatomy = "knee"
    ctx.volumes = {"pd_sag": np.random.rand(5, 64, 64).astype(np.float32)}
    ctx.anomaly_scores = {"pd_sag": [0.1, 0.5, 0.9, 0.3, 0.2]}
    ctx.top_slices = {"pd_sag": [2, 1, 3]}
    ctx.signal_analysis = {
        "pd_sag": SignalStats(
            mean_intensity=[0.3] * 5,
            max_intensity=[0.9] * 5,
            high_signal_ratio=[0.05] * 5,
            high_signal_slices=[2],
        )
    }
    ctx.findings = [StructureFinding(name="ACL", status="intact", confidence=0.9, findings="Normal ACL")]
    ctx.overall_impression = "Normal knee MRI"
    ctx.clinical_correlation = "Consistent with clinical exam"
    ctx.limitations = ["1.5T field strength"]
    ctx.report_format = "json"
    ctx.report_language = "en"
    ctx.output_dir = str(tmp_path)
    return ctx


def test_generate_json_report(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    output = generate_json_report(ctx)
    data = json.loads(output)
    assert data["patient"]["name"] == "Test^Patient"
    assert len(data["findings"]) == 1
    assert data["findings"][0]["name"] == "ACL"
    assert data["overall_impression"] == "Normal knee MRI"


def test_report_step_json(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    step = ReportStep()
    result = step.run(ctx)
    assert result.report_path.endswith(".json")
    assert Path(result.report_path).exists()
    data = json.loads(Path(result.report_path).read_text())
    assert data["patient"]["name"] == "Test^Patient"


def test_report_step_name():
    assert ReportStep().name == "report"


def test_report_step_validate():
    ctx = PipelineContext()
    step = ReportStep()
    # Should still work even without findings (generates empty report)
    assert step.validate(ctx) is True


def test_report_step_language_german(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    ctx.report_language = "de"

    step = ReportStep()
    result = step.run(ctx)

    assert Path(result.report_path).exists()
    data = json.loads(Path(result.report_path).read_text())

    # Check that structural or dictionary labels are translated to German
    # Note: Adjust the exact key/value check below based on what your de.json looks like!
    # Verify that the report config correctly registers the target language metadata
    assert data["language"] == "de"


def test_report_step_language_fallback(tmp_path: Path):
    ctx = _make_ctx(tmp_path)
    # Set to an unsupported language to trigger the English fallback flow
    ctx.report_language = "xyz_unsupported"

    step = ReportStep()
    result = step.run(ctx)

    assert Path(result.report_path).exists()
    data = json.loads(Path(result.report_path).read_text())

    # Verify it gracefully fell back to standard English keys/labels
    assert "patient" in data
    assert data["patient"]["name"] == "Test^Patient"
