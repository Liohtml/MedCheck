import numpy as np
import pytest

from medcheck.core.context import PipelineContext
from medcheck.pipeline.ml_analysis import MLAnalysisStep, analyze_signal_intensity, compute_anomaly_scores


def test_compute_anomaly_scores():
    features = np.random.randn(10, 512).astype(np.float32)
    # Make one slice very different
    features[5] = features[5] * 10
    scores = compute_anomaly_scores(features)
    assert len(scores) == 10
    assert scores.min() >= 0.0
    assert scores.max() <= 1.0
    assert scores[5] == pytest.approx(1.0, abs=0.01)


def test_analyze_signal_intensity():
    volume = np.random.rand(10, 64, 64).astype(np.float32)
    # Make slice 3 very bright
    volume[3] = volume[3] * 5
    result = analyze_signal_intensity(volume)
    assert len(result.mean_intensity) == 10
    assert len(result.high_signal_ratio) == 10
    assert result.mean_intensity[3] > result.mean_intensity[0]


def test_ml_step_runs_on_volumes():
    ctx = PipelineContext()
    ctx.volumes = {
        "test_series": np.random.rand(5, 64, 64).astype(np.float32),
    }

    step = MLAnalysisStep()
    result = step.run(ctx)

    assert "test_series" in result.anomaly_scores
    assert len(result.anomaly_scores["test_series"]) == 5
    assert "test_series" in result.top_slices
    assert len(result.top_slices["test_series"]) <= 5
    assert "test_series" in result.signal_analysis


def test_ml_step_validate_no_volumes():
    ctx = PipelineContext()
    step = MLAnalysisStep()
    assert step.validate(ctx) is False


def test_ml_step_validate_with_volumes():
    ctx = PipelineContext()
    ctx.volumes = {"series": np.zeros((3, 64, 64))}
    step = MLAnalysisStep()
    assert step.validate(ctx) is True


def test_ml_step_name():
    assert MLAnalysisStep().name == "ml_analysis"
