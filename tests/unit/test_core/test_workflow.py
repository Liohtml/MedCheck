import pytest

from medcheck.core.context import PipelineContext
from medcheck.core.step import PipelineStep
from medcheck.core.workflow import StepRegistry, WorkflowEngine


class FakeIngest(PipelineStep):
    name = "ingest"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.detected_anatomy = "knee"
        return context


class FakeReport(PipelineStep):
    name = "report"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.report_path = "/tmp/report.pdf"
        return context


def test_workflow_engine_runs_steps_in_order():
    registry = StepRegistry()
    registry.register("ingest", FakeIngest)
    registry.register("report", FakeReport)
    engine = WorkflowEngine(registry=registry)
    ctx = engine.run(steps=["ingest", "report"], context=PipelineContext())
    assert ctx.detected_anatomy == "knee"
    assert ctx.report_path == "/tmp/report.pdf"


def test_workflow_engine_from_yaml(tmp_path):
    workflow_file = tmp_path / "test.yml"
    workflow_file.write_text("name: test\nsteps:\n  - ingest:\n  - report:\n")
    registry = StepRegistry()
    registry.register("ingest", FakeIngest)
    registry.register("report", FakeReport)
    engine = WorkflowEngine(registry=registry)
    ctx = engine.run_from_yaml(str(workflow_file), context=PipelineContext())
    assert ctx.detected_anatomy == "knee"
    assert ctx.report_path == "/tmp/report.pdf"


def test_registry_unknown_step_raises():
    registry = StepRegistry()
    engine = WorkflowEngine(registry=registry)
    with pytest.raises(KeyError, match="ingest"):
        engine.run(steps=["ingest"], context=PipelineContext())


def test_registry_list_steps():
    registry = StepRegistry()
    registry.register("ingest", FakeIngest)
    registry.register("report", FakeReport)
    assert registry.list_steps() == ["ingest", "report"]


def test_workflow_records_completed_steps_and_missing_prerequisites():
    class NotReady(PipelineStep):
        name = "not_ready"

        def validate(self, context):
            return False

        def run(self, context):
            raise AssertionError("A step without prerequisites must not execute")

    registry = StepRegistry()
    registry.register("ingest", FakeIngest)
    registry.register("not_ready", NotReady)
    ctx = WorkflowEngine(registry).run(["not_ready", "ingest"], PipelineContext())
    assert any("not_ready" in message and "prerequisites" in message for message in ctx.limitations)
    assert ctx.analysis_provenance["app_version"]
    assert ctx.analysis_provenance["started_at"]
    assert [step["name"] for step in ctx.analysis_provenance["steps"]] == ["ingest"]
    assert ctx.analysis_provenance["steps"][0]["seconds"] >= 0


def test_workflow_deidentifies_before_preprocess_and_masks_before_analysis():
    from unittest.mock import patch

    import numpy as np

    from medcheck.core.context import DicomSeries, PatientInfo

    class InspectPreprocess(PipelineStep):
        name = "preprocess"

        def run(self, context):
            assert context.patient.patient_id != "ID123"
            assert context.dicom_series[0].description == "Series 1"
            assert context.clinical_context.anatomy == "knee"
            context.volumes["Series 1"] = np.ones((2, 4, 4))
            return context

    class InspectAnalysis(PipelineStep):
        name = "analysis"

        def run(self, context):
            assert np.all(context.volumes["Series 1"][:, 0, :2] == 0)
            assert "ocr_redactions" in context.analysis_provenance
            return context

    registry = StepRegistry()
    registry.register("preprocess", InspectPreprocess)
    registry.register("analysis", InspectAnalysis)
    ctx = PipelineContext(
        deidentify=True,
        patient=PatientInfo(patient_id="ID123"),
        dicom_series=[DicomSeries(description="knee")],
        analysis_provenance={"ocr_requested": True},
    )
    with patch("medcheck.pipeline.privacy._ocr_rectangles", return_value=[[0, 0, 2, 1]]) as ocr:
        result = WorkflowEngine(registry).run(["preprocess", "analysis"], ctx)
    assert ocr.call_count == 2
    assert result.pixels_reviewed is False
    assert [item["name"] for item in result.analysis_provenance["steps"]] == ["preprocess", "analysis"]


def test_preprocess_ocr_config_is_honored_without_mutating_caller_config():
    from unittest.mock import patch

    import numpy as np

    class FakePreprocess(PipelineStep):
        name = "preprocess"

        def run(self, context):
            context.volumes["series"] = np.ones((1, 4, 4))
            return context

    registry = StepRegistry()
    registry.register("preprocess", FakePreprocess)
    config = {"preprocess": {"ocr": True}}
    with patch("medcheck.pipeline.privacy._ocr_rectangles", return_value=[[0, 0, 1, 1]]) as ocr:
        ctx = WorkflowEngine(registry).run(["preprocess"], PipelineContext(), config)
    ocr.assert_called_once()
    assert ctx.volumes["series"][0, 0, 0] == 0
    ctx.step_config["extra"] = "local"
    assert config == {"preprocess": {"ocr": True}}


def test_report_only_workflow_scrubs_preexisting_findings_before_report():
    from medcheck.core.context import PatientInfo, StructureFinding
    from medcheck.pipeline.report import generate_json_report

    class InspectReport(PipelineStep):
        name = "report"

        def run(self, context):
            serialized = generate_json_report(context)
            assert "ID123" not in serialized
            assert "Jane" not in serialized
            return context

    registry = StepRegistry()
    registry.register("report", InspectReport)
    ctx = PipelineContext(
        deidentify=True,
        patient=PatientInfo(name="Doe^Jane", patient_id="ID123"),
        findings=[StructureFinding(name="ACL", findings="ID123 Jane Doe")],
    )
    result = WorkflowEngine(registry).run(["report"], ctx)
    assert result.analysis_provenance["deidentification"]["metadata_deidentified"] is True
