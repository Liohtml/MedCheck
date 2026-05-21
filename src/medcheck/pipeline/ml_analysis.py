"""ML Analysis step - local feature extraction and anomaly detection.

Uses ResNet18 pretrained on ImageNet for feature extraction.
No API key required.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from rich.console import Console

from medcheck.core.context import PipelineContext, SignalStats
from medcheck.core.step import PipelineStep

console = Console()


def compute_anomaly_scores(features: np.ndarray) -> np.ndarray:
    """Per-slice anomaly score = normalized distance from mean feature vector."""
    mean_feat = features.mean(axis=0)
    distances = np.linalg.norm(features - mean_feat, axis=1)
    dmin, dmax = distances.min(), distances.max()
    if dmax - dmin > 0:
        return (distances - dmin) / (dmax - dmin)
    return np.zeros(len(distances), dtype=np.float32)


def analyze_signal_intensity(volume: np.ndarray) -> SignalStats:
    """Analyze per-slice signal intensity. High signal on PD FS = fluid/edema."""
    mean_int = [float(volume[i].mean()) for i in range(volume.shape[0])]
    max_int = [float(volume[i].max()) for i in range(volume.shape[0])]
    high_ratio = [float((volume[i] > np.percentile(volume[i], 95)).mean()) for i in range(volume.shape[0])]

    mean_hr = np.mean(high_ratio)
    std_hr = np.std(high_ratio)
    high_slices = list(np.where(np.array(high_ratio) > mean_hr + 1.5 * std_hr)[0].astype(int))

    return SignalStats(
        mean_intensity=mean_int,
        max_intensity=max_int,
        high_signal_ratio=high_ratio,
        high_signal_slices=high_slices,
    )


def extract_features(volume: np.ndarray) -> np.ndarray:
    """Extract features per slice using ResNet18 or fallback to simple stats."""
    try:
        import torch
        from torchvision import models, transforms

        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        feature_extractor = torch.nn.Sequential(*list(model.children())[:-1])
        feature_extractor.requires_grad_(False)

        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

        features = []
        with torch.no_grad():
            for i in range(volume.shape[0]):
                sl = volume[i]
                sl_uint8 = ((sl - sl.min()) / (sl.max() - sl.min() + 1e-8) * 255).astype(np.uint8)
                img = Image.fromarray(sl_uint8).convert("RGB")
                tensor = transform(img).unsqueeze(0)
                feat = feature_extractor(tensor).squeeze().numpy()
                features.append(feat)
        return np.array(features)

    except ImportError:
        # Fallback: simple statistical features when PyTorch not installed
        console.print("[yellow]PyTorch not available, using simple statistical features[/yellow]")
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


class MLAnalysisStep(PipelineStep):
    """Local ML analysis: feature extraction + anomaly scoring + signal analysis."""

    name = "ml_analysis"

    def validate(self, context: PipelineContext) -> bool:
        return bool(context.volumes)

    def run(self, context: PipelineContext) -> PipelineContext:
        for series_name, volume in context.volumes.items():
            console.print(f"  [blue]Analyzing {series_name} ({volume.shape[0]} slices)...[/blue]")

            # Feature extraction + anomaly scores
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
