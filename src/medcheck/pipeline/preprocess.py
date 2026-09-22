from __future__ import annotations

import re
from collections import Counter
from typing import Any

import numpy as np
from rich.console import Console

from medcheck.core.context import DicomSeries, PipelineContext
from medcheck.core.step import PipelineStep

console = Console()

# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

_ANATOMY_PATTERNS: list[tuple[str, str]] = [
    # spine checked first so lumbar_spine_* does not match knee pattern via sag
    (r"spine|lumbar|cervical|thoracic|wirbel", "spine"),
    (r"knee|knie|pd_tse|tse_fs", "knee"),
    (r"shoulder|schulter", "shoulder"),
    (r"hip|hüfte|huefte|femoroacetabular", "hip"),
    (r"ankle|sprunggelenk|achilles|foot|fuß|fuss|calcaneus|hindfoot", "ankle"),
    (r"wrist|handgelenk|carpal|tfcc|scaphoid", "wrist"),
]

_PLANE_PATTERNS: list[tuple[str, str]] = [
    (r"sag", "sagittal"),
    (r"cor", "coronal"),
    (r"tra|axi|transv", "axial"),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def detect_anatomy(description: str) -> str:
    """Return the anatomy keyword inferred from *description*, or 'unknown'."""
    lower = description.lower()
    for pattern, label in _ANATOMY_PATTERNS:
        if re.search(pattern, lower):
            return label
    return "unknown"


def detect_plane(description: str) -> str:
    """Return the imaging plane inferred from *description*, or 'unknown'."""
    lower = description.lower()
    for pattern, label in _PLANE_PATTERNS:
        if re.search(pattern, lower):
            return label
    return "unknown"


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def _sort_key(ds: Any) -> float:
    """Return a numeric sort key for a DICOM slice dataset."""
    loc = getattr(ds, "SliceLocation", None)
    if loc is not None:
        try:
            return float(loc)
        except (TypeError, ValueError):
            pass
    num = getattr(ds, "InstanceNumber", None)
    if num is not None:
        try:
            return float(num)
        except (TypeError, ValueError):
            pass
    return 0.0


def _slice_normal(ds: Any) -> np.ndarray | None:
    try:
        orientation = np.asarray(ds.ImageOrientationPatient, dtype=float)
        normal = np.cross(orientation[:3], orientation[3:])
        length = np.linalg.norm(normal)
        return normal / length if length > 0 and np.isfinite(normal).all() else None
    except (AttributeError, TypeError, ValueError):
        return None


def _position(ds: Any, normal: np.ndarray) -> float | None:
    try:
        result = float(np.dot(np.asarray(ds.ImagePositionPatient, dtype=float), normal))
        return result if np.isfinite(result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _extract_pixel_array(ds: Any) -> np.ndarray[Any, np.dtype[Any]]:
    """Decode with pydicom's transfer syntax handling; never guess raw encoding."""
    from pydicom.pixels.processing import apply_modality_lut

    array = np.asarray(apply_modality_lut(ds.pixel_array, ds), dtype=np.float32)
    if array.ndim != 2 or int(getattr(ds, "SamplesPerPixel", 1)) != 1:
        raise ValueError("only single-frame grayscale DICOM images are supported")
    if not np.isfinite(array).all():
        raise ValueError("pixel values are non-finite")
    if getattr(ds, "PhotometricInterpretation", "") == "MONOCHROME1":
        array = array.max() + array.min() - array
    return array


def _build_volume(series: DicomSeries) -> np.ndarray:
    """Build a normalized volume while retaining quality warnings and source mapping."""
    if not series.slices:
        raise ValueError("series contains no slices")
    warnings: list[str] = []
    normal = _slice_normal(series.slices[0])
    positions = [_position(ds, normal) for ds in series.slices] if normal is not None else []
    normals = [_slice_normal(ds) for ds in series.slices]
    orientation_ok = normal is not None and all(n is not None and np.allclose(n, normal, atol=1e-3) for n in normals)
    if normal is not None and not orientation_ok:
        raise ValueError("inconsistent image orientations; split the localizers from this series")
    use_geometry = orientation_ok and all(pos is not None for pos in positions)
    if not use_geometry:
        warnings.append("Missing image geometry; slice ordering uses SliceLocation/InstanceNumber.")
    ordered = sorted(
        enumerate(series.slices),
        key=lambda item: float(positions[item[0]] or 0) if use_geometry else _sort_key(item[1]),
    )
    decoded = [(index, ds, _extract_pixel_array(ds)) for index, ds in ordered]
    counts = Counter(arr.shape for _, _, arr in decoded)
    if len(counts) > 1:
        dominant = counts.most_common(1)[0][0]
        kept = [item for item in decoded if item[2].shape == dominant]
        warnings.append(f"Dropped {len(decoded) - len(kept)} slice(s) with deviating dimensions.")
        decoded = kept
    if use_geometry and len(decoded) > 1:
        spacing = np.diff([positions[index] for index, _, _ in decoded])
        if np.any(spacing < 1e-4):
            warnings.append("Duplicate slice positions detected; volume may contain repeated acquisitions.")
        positive = spacing[spacing > 1e-4]
        if len(positive) > 1 and not np.allclose(positive, np.median(positive), rtol=0.1, atol=0.1):
            warnings.append("Irregular slice spacing or missing slices detected.")
    series.metadata["quality_checks"] = warnings
    series.metadata["slice_references"] = [
        {
            "original_index": index,
            "sop_instance_uid": str(getattr(ds, "SOPInstanceUID", "")),
            "instance_number": str(getattr(ds, "InstanceNumber", "")),
        }
        for index, ds, _ in decoded
    ]
    volume = np.stack([arr for _, _, arr in decoded], axis=0)
    lo, hi = volume.min(), volume.max()
    return (volume - lo) / (hi - lo) if hi > lo else np.zeros_like(volume)


def _series_keys(series_list: list[DicomSeries]) -> list[str]:
    """Return one unique, human-readable key per series.

    SeriesDescription (0008,103E) is optional and frequently empty or repeated
    across series, so it cannot be used as a dict key directly — colliding
    series would silently overwrite each other downstream (volumes, anomaly
    scores, report sections). Unique descriptions are kept verbatim; empty
    ones fall back to the series number, and duplicates get a numeric suffix.
    """
    keys: list[str] = []
    used: set[str] = set()
    for index, series in enumerate(series_list):
        base = series.description or f"series-{series.series_number or index + 1}"
        key = base
        suffix = 2
        while key in used:
            key = f"{base} ({suffix})"
            suffix += 1
        used.add(key)
        keys.append(key)
    return keys


class PreprocessStep(PipelineStep):
    """Build normalised numpy volumes from raw DICOM series."""

    name: str = "preprocess"

    def run(self, context: PipelineContext) -> PipelineContext:
        # All downstream per-series dicts (volumes, detected_planes, and the
        # ml/vision results keyed off context.volumes) share these keys.
        keys = _series_keys(context.dicom_series)

        for key, series in zip(keys, context.dicom_series, strict=True):
            try:
                context.volumes[key] = _build_volume(series)
                context.slice_references[key] = series.metadata["slice_references"]
                context.quality_checks[key] = series.metadata["quality_checks"]
                context.limitations.extend(f"Series '{key}': {warning}" for warning in context.quality_checks[key])
            except Exception as exc:
                # One malformed series must not abort the whole study; surface
                # the gap in the report's limitations instead.
                message = f"Series '{key}' skipped during preprocessing: {exc}"
                console.print(f"[yellow]{message}[/yellow]")
                context.limitations.append(message)
                context.quality_checks[key] = [message]

        # Detect anatomy from the first series description
        if context.dicom_series:
            first_desc = context.dicom_series[0].description
            context.detected_anatomy = detect_anatomy(first_desc)

        # Detect plane for every series (from the real description, keyed by
        # the same unique key as the volume)
        for key, series in zip(keys, context.dicom_series, strict=True):
            normal = _slice_normal(series.slices[0]) if series.slices else None
            context.detected_planes[key] = (
                ("sagittal", "coronal", "axial")[int(np.argmax(np.abs(normal)))]
                if normal is not None
                else detect_plane(series.description)
            )

        if context.clinical_context and context.clinical_context.anatomy:
            context.detected_anatomy = context.clinical_context.anatomy

        return context
