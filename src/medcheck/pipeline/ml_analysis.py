"""ML Analysis step - local feature extraction and anomaly detection.

Uses ResNet18 pretrained on ImageNet for feature extraction.
No API key required.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import numpy as np
from PIL import Image
from rich.console import Console

from medcheck.core.context import PipelineContext, SignalStats
from medcheck.core.step import PipelineStep

console = Console()

_feature_extractor = None
# Guards lazy initialization of the module-level singleton. Without it, two
# concurrent requests (e.g. under uvicorn) could both pass the `is None` check
# and build the model twice, wasting memory and racing on the global.
_feature_extractor_lock = threading.Lock()


def _build_feature_extractor() -> Any:
    """Construct the ResNet18 feature extractor (imports torch lazily)."""
    import torch
    from torchvision import models

    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    extractor = torch.nn.Sequential(*list(model.children())[:-1])
    extractor.requires_grad_(False)
    extractor.eval()
    extractor.to(os.environ.get("MEDCHECK_ML_DEVICE", "cpu"))
    return extractor


def _get_feature_extractor() -> Any:
    global _feature_extractor
    # Double-checked locking: the fast path avoids the lock once initialized,
    # while the lock makes the first-time build safe under concurrency.
    if _feature_extractor is None:
        with _feature_extractor_lock:
            if _feature_extractor is None:
                _feature_extractor = _build_feature_extractor()
    return _feature_extractor


def compute_anomaly_scores(features: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[Any]]:
    """Per-slice anomaly score = normalized distance from mean feature vector."""
    mean_feat = features.mean(axis=0)
    distances = np.linalg.norm(features - mean_feat, axis=1)
    dmin, dmax = distances.min(), distances.max()
    if dmax - dmin > 0:
        result: np.ndarray[Any, np.dtype[Any]] = (distances - dmin) / (dmax - dmin)
        return result
    zeros: np.ndarray[Any, np.dtype[Any]] = np.zeros(len(distances), dtype=np.float32)
    return zeros


def analyze_signal_intensity(volume: np.ndarray) -> SignalStats:
    """Describe intensity using one volume-wide foreground threshold; not diagnostic."""
    mean_int = [float(volume[i].mean()) for i in range(volume.shape[0])]
    max_int = [float(volume[i].max()) for i in range(volume.shape[0])]
    foreground = volume[volume > volume.min()]
    threshold = float(np.percentile(foreground, 95)) if foreground.size else float(volume.max())
    high_ratio = [float((volume[i] > threshold).mean()) for i in range(volume.shape[0])]

    mean_hr = np.mean(high_ratio)
    std_hr = np.std(high_ratio)
    high_slices = list(np.where(np.array(high_ratio) > mean_hr + 1.5 * std_hr)[0].astype(int))

    return SignalStats(
        mean_intensity=mean_int,
        max_intensity=max_int,
        high_signal_ratio=high_ratio,
        high_signal_slices=high_slices,
    )


def _resnet_features(volume: np.ndarray) -> np.ndarray:
    """Extract per-slice features with the ResNet18 extractor (needs torch)."""
    import torch
    from torchvision import transforms

    feature_extractor = _get_feature_extractor()

    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    batch_size = max(1, min(128, int(os.environ.get("MEDCHECK_ML_BATCH_SIZE", "16"))))
    device = next(feature_extractor.parameters()).device
    features = []
    with torch.inference_mode():
        for start in range(0, volume.shape[0], batch_size):
            tensors = []
            for sl in volume[start : start + batch_size]:
                sl_uint8 = (np.clip(sl, 0, 1) * 255).astype(np.uint8)
                tensors.append(transform(Image.fromarray(sl_uint8).convert("RGB")))
            batch = torch.stack(tensors).to(device)
            features.append(feature_extractor(batch).flatten(1).cpu().numpy())
    return np.concatenate(features, axis=0)


def _statistical_features(volume: np.ndarray) -> np.ndarray:
    """Per-slice statistical features — the no-torch / offline fallback."""
    features = []
    for i in range(volume.shape[0]):
        sl = volume[i]
        feat = np.array(
            [
                sl.mean(),
                sl.std(),
                sl.min(),
                sl.max(),
                np.percentile(sl, 25),
                np.percentile(sl, 50),
                np.percentile(sl, 75),
                np.percentile(sl, 95),
                np.percentile(sl, 99),
                (sl > sl.mean()).mean(),
            ],
            dtype=np.float32,
        )
        features.append(feat)
    return np.array(features)


def extract_features(volume: np.ndarray) -> np.ndarray:
    """Extract features per slice using ResNet18 or fallback to simple stats."""
    try:
        return _resnet_features(volume)
    except Exception as exc:
        # The ResNet path is best-effort: torch may be missing (ImportError),
        # or the one-time ImageNet weight download may fail in an air-gapped
        # environment (URLError/OSError/RuntimeError). Any of these must
        # degrade to the statistical features, not crash the analysis step.
        reason = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        console.print(
            f"[yellow]Local ML feature extractor unavailable ({reason}); using simple statistical features[/yellow]"
        )
        return _statistical_features(volume)


class MLAnalysisStep(PipelineStep):
    """Local ML analysis: feature extraction + anomaly scoring + signal analysis."""

    name = "ml_analysis"

    def validate(self, context: PipelineContext) -> bool:
        return bool(context.volumes)

    def run(self, context: PipelineContext) -> PipelineContext:
        note = (
            "Local anomaly scores are relative within each series, not disease probabilities. "
            "Signal statistics describe brightness and do not establish a diagnosis."
        )
        if note not in context.limitations:
            context.limitations.append(note)
        backend = context.step_config.get("backend", "auto")
        if backend not in {"auto", "statistical", "resnet"}:
            raise ValueError("ML backend must be auto, statistical, or resnet")
        context.analysis_provenance["ml_backend_requested"] = backend
        for series_name, volume in context.volumes.items():
            console.print(f"  [blue]Analyzing {series_name} ({volume.shape[0]} slices)...[/blue]")

            # Feature extraction + anomaly scores
            if backend == "statistical":
                features = _statistical_features(volume)
            elif backend == "resnet":
                features = _resnet_features(volume)
            else:
                features = extract_features(volume)
            scores = compute_anomaly_scores(features)
            context.anomaly_scores[series_name] = scores.tolist()

            # Top suspicious slices
            n_top = min(5, len(scores))
            top = np.argsort(scores)[-n_top:][::-1].tolist()
            context.top_slices[series_name] = top

            # Signal analysis
            signal = analyze_signal_intensity(volume)
            context.signal_analysis[series_name] = signal

        return context
