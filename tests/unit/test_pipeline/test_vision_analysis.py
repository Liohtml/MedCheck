from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from medcheck.core.context import ClinicalContext, PipelineContext, StructureFinding
from medcheck.llm.base import AnalysisResult
from medcheck.pipeline.vision_analysis import (
    VisionAnalysisStep,
    build_prompt,
    load_anatomy_instructions,
)


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


def test_load_anatomy_instructions_uses_template_file():
    # knee.txt ships with a detailed checklist that the dict hint does not contain.
    instructions = load_anatomy_instructions("knee")
    assert "ANTERIOR CRUCIATE LIGAMENT" in instructions


def test_load_anatomy_instructions_falls_back_to_hint():
    # "brain" has a built-in hint but no template file.
    instructions = load_anatomy_instructions("brain")
    assert "diffusion restriction" in instructions


def test_load_anatomy_instructions_generic_fallback():
    instructions = load_anatomy_instructions("elbow")
    assert "elbow" in instructions.lower()


def test_load_anatomy_instructions_abdomen_hint():
    instructions = load_anatomy_instructions("abdomen")
    assert "liver" in instructions.lower()


def test_load_anatomy_instructions_rejects_path_traversal():
    # A traversal attempt must not read files outside the template dir; it
    # falls through to the generic instruction instead.
    instructions = load_anatomy_instructions("../../../etc/passwd")
    assert "Thoroughly evaluate" in instructions


def test_build_prompt_includes_detailed_template():
    prompt = build_prompt(None, "knee")
    # Detailed template content (not just the short dict hint) must reach the prompt.
    assert "MEDIAL MENISCUS" in prompt


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
    ctx.allow_external_llm = True  # consent to the cloud provider

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


def _consent_test_context():
    ctx = PipelineContext()
    ctx.volumes = {"s": np.random.rand(3, 32, 32).astype(np.float32)}
    ctx.top_slices = {"s": [0, 1]}
    ctx.detected_anatomy = "knee"
    return ctx


def test_vision_step_blocks_cloud_without_consent():
    ctx = _consent_test_context()  # allow_external_llm defaults to False

    cloud_provider = MagicMock()
    cloud_provider.name = "claude"
    mock_router = MagicMock()
    mock_router.select.return_value = cloud_provider

    step = VisionAnalysisStep()
    with patch.object(step, "_get_router", return_value=mock_router):
        with pytest.raises(PermissionError, match="external"):
            step.run(ctx)
    cloud_provider.analyze_images.assert_not_called()


def test_vision_step_allows_local_without_consent():
    ctx = _consent_test_context()  # no consent, but provider is local

    local_provider = MagicMock()
    local_provider.name = "local"
    local_provider.analyze_images.return_value = AnalysisResult(overall_impression="ok", raw_response="{}")
    mock_router = MagicMock()
    mock_router.select.return_value = local_provider

    step = VisionAnalysisStep()
    with patch.object(step, "_get_router", return_value=mock_router):
        result = step.run(ctx)
    assert result.overall_impression == "ok"
    local_provider.analyze_images.assert_called_once()
    # Without consent, selection must default to the on-device provider.
    assert mock_router.select.call_args.kwargs.get("preferred") == "local"


def test_vision_step_honours_explicit_provider_preference():
    ctx = _consent_test_context()
    ctx.allow_external_llm = True
    ctx.llm_provider = "gemini"

    provider = MagicMock()
    provider.name = "gemini"
    provider.analyze_images.return_value = AnalysisResult(overall_impression="ok", raw_response="{}")
    mock_router = MagicMock()
    mock_router.select.return_value = provider

    step = VisionAnalysisStep()
    with patch.object(step, "_get_router", return_value=mock_router):
        step.run(ctx)
    assert mock_router.select.call_args.kwargs.get("preferred") == "gemini"
