from medcheck.core.context import PipelineContext
from medcheck.core.step import PipelineStep


class DummyStep(PipelineStep):
    name = "dummy"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.detected_anatomy = "knee"
        return context


def test_step_interface():
    step = DummyStep()
    assert step.name == "dummy"
    assert step.validate(PipelineContext()) is True


def test_step_run():
    step = DummyStep()
    ctx = PipelineContext()
    result = step.run(ctx)
    assert result.detected_anatomy == "knee"
