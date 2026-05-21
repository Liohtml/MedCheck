from unittest.mock import MagicMock, patch

import numpy as np

from medcheck.core.context import ClinicalContext, PipelineContext, StructureFinding
from medcheck.llm.base import AnalysisResult
from medcheck.pipeline.vision_analysis import VisionAnalysisStep, build_prompt


def test_build_prompt_with_clinical_context():
    cc = ClinicalContext(
        symptoms="Medial knee pain",
        trauma="Valgus stress BJJ",
        anatomy="knee",
    )
    prompt = build_prompt(cc, "knee")
    assert "knee" in prompt.lower()
    assert "Medial knee pain" in prompt
    assert "Valgus stress" in prompt


def test_build_prompt_without_context():
    prompt = build_prompt(None, "knee")
    assert "knee" in prompt.lower()
    assert "No clinical context" in prompt or "clinical" in prompt.lower()


def test_vision_step_name():
    assert VisionAnalysisStep().name == "vision_analysis"


def test_vision_step_validate_no_volumes():
    ctx = PipelineContext()
    step = VisionAnalysisStep()
    assert step.validate(ctx) is False


def test_vision_step_validate_with_volumes():
    ctx = PipelineContext()
    ctx.volumes = {"test": np.zeros((5, 64, 64))}
    step = VisionAnalysisStep()
    assert step.validate(ctx) is True


def test_vision_step_populates_findings():
    ctx = PipelineContext()
    ctx.volumes = {"test_sag": np.random.rand(5, 64, 64).astype(np.float32)}
    ctx.top_slices = {"test_sag": [2, 3, 1]}
    ctx.detected_anatomy = "knee"

    mock_result = AnalysisResult(
        structures=[StructureFinding(name="ACL", status="intact", confidence=0.9, findings="Normal")],
        overall_impression="Normal knee",
        clinical_correlation="Consistent",
        limitations=["1.5T"],
        raw_response="{}",
    )

    mock_provider = MagicMock()
    mock_provider.analyze_images.return_value = mock_result
    mock_provider.name = "mock"

    mock_router = MagicMock()
    mock_router.select.return_value = mock_provider

    step = VisionAnalysisStep()
    with patch.object(step, "_get_router", return_value=mock_router):
        result = step.run(ctx)

    assert len(result.findings) == 1
    assert result.findings[0].name == "ACL"
    assert result.overall_impression == "Normal knee"
