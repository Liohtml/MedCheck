import threading
import time
from unittest.mock import patch

import numpy as np
import pytest

import medcheck.pipeline.ml_analysis as ml_analysis
from medcheck.core.context import PipelineContext
from medcheck.pipeline.ml_analysis import MLAnalysisStep, analyze_signal_intensity, compute_anomaly_scores


def test_get_feature_extractor_builds_once_under_concurrency():
    # Concurrent first-time access must build the singleton exactly once (no race).
    call_count = 0

    def slow_build():
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)  # widen the race window
        return object()

    with (
        patch.object(ml_analysis, "_feature_extractor", None),
        patch.object(ml_analysis, "_build_feature_extractor", side_effect=slow_build),
    ):
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(ml_analysis._get_feature_extractor())) for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert call_count == 1
    # All callers get the same instance.
    assert len({id(r) for r in results}) == 1


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
