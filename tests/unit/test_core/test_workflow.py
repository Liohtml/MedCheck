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
