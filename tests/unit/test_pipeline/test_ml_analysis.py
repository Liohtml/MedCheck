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
    ctx = PipelineContext(step_config={"backend": "statistical"})
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


def test_extract_features_falls_back_when_resnet_path_fails():
    """A weight-download failure (not just missing torch) must degrade gracefully."""
    volume = np.random.rand(3, 16, 16).astype(np.float32)
    with patch.object(ml_analysis, "_resnet_features", side_effect=RuntimeError("download.pytorch.org unreachable")):
        features = ml_analysis.extract_features(volume)
    assert features.shape == (3, 10)  # statistical fallback: 10 features per slice


def test_extract_features_falls_back_on_import_error():
    volume = np.random.rand(2, 16, 16).astype(np.float32)
    with patch.object(ml_analysis, "_resnet_features", side_effect=ImportError("No module named 'torch'")):
        features = ml_analysis.extract_features(volume)
    assert features.shape == (2, 10)


def test_signal_uses_shared_threshold_to_distinguish_bright_slices():
    volume = np.tile(np.linspace(0, 1, 64).reshape(8, 8), (10, 1, 1))
    volume[3] *= 5
    stats = analyze_signal_intensity(volume)
    assert stats.high_signal_ratio[3] > 0.4
    assert stats.high_signal_ratio[0] == 0
    assert 3 in stats.high_signal_slices


def test_statistical_backend_never_initializes_resnet_or_downloads():
    ctx = PipelineContext(volumes={"s": np.ones((2, 8, 8))}, step_config={"backend": "statistical"})
    with patch.object(ml_analysis, "_resnet_features") as resnet:
        MLAnalysisStep().run(ctx)
    resnet.assert_not_called()
    assert ctx.analysis_provenance["ml_backend_requested"] == "statistical"
    assert len(ctx.anomaly_scores["s"]) == 2


def test_resnet_eval_and_batch_size_invariance_without_weight_download(monkeypatch):
    torch = pytest.importorskip("torch")
    torchvision = pytest.importorskip("torchvision")
    real_resnet18 = torchvision.models.resnet18
    requested_weights = []

    def offline_resnet18(*, weights):
        requested_weights.append(weights)
        torch.manual_seed(42)
        return real_resnet18(weights=None)

    monkeypatch.setattr(torchvision.models, "resnet18", offline_resnet18)
    monkeypatch.setenv("MEDCHECK_ML_DEVICE", "cpu")
    extractor = ml_analysis._build_feature_extractor()
    assert requested_weights == [torchvision.models.ResNet18_Weights.IMAGENET1K_V1]
    assert all(not module.training for module in extractor.modules())
    assert all(not parameter.requires_grad for parameter in extractor.parameters())
    assert next(extractor.parameters()).device.type == "cpu"
    monkeypatch.setattr(ml_analysis, "_feature_extractor", extractor)
    volume = np.random.default_rng(123).random((4, 32, 32), dtype=np.float32)
    original_threads = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        monkeypatch.setenv("MEDCHECK_ML_BATCH_SIZE", "1")
        single = ml_analysis._resnet_features(volume)
        monkeypatch.setenv("MEDCHECK_ML_BATCH_SIZE", "3")
        batched = ml_analysis._resnet_features(volume)
    finally:
        torch.set_num_threads(original_threads)
    assert single.shape == batched.shape == (4, 512)
    assert np.isfinite(single).all()
    assert not np.array_equal(single[0], single[1])
    np.testing.assert_allclose(single, batched, rtol=1e-4, atol=1e-5)
