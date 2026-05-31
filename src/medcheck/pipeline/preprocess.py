from __future__ import annotations

import re
from typing import Any

import numpy as np

from medcheck.core.context import DicomSeries, PipelineContext
from medcheck.core.step import PipelineStep

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


def _extract_pixel_array(ds: Any) -> np.ndarray[Any, np.dtype[Any]]:
    """Extract the 2-D pixel array from a DICOM dataset.

    Tries ``ds.pixel_array`` first (requires pydicom with correct transfer
    syntax).  Falls back to reconstructing from raw ``PixelData`` bytes when
    the standard path raises an exception (e.g. missing file meta in pure
    in-memory ``Dataset`` objects used in tests).
    """
    try:
        arr_f: np.ndarray[Any, np.dtype[Any]] = ds.pixel_array.astype(np.float32)
        return arr_f
    except Exception:
        rows = int(ds.Rows)
        cols = int(ds.Columns)
        bits = int(getattr(ds, "BitsAllocated", 16))
        dtype = np.uint16 if bits == 16 else np.uint8
        raw = bytes(ds.PixelData)
        arr = np.frombuffer(raw, dtype=dtype).reshape(rows, cols)
        return arr.astype(np.float32)


def _build_volume(series: DicomSeries) -> np.ndarray:
    """Sort slices, extract pixel arrays, stack, and normalise to [0, 1]."""
    sorted_slices = sorted(series.slices, key=_sort_key)
    arrays = [_extract_pixel_array(ds) for ds in sorted_slices]
    volume = np.stack(arrays, axis=0)  # shape: (N, H, W)

    v_min = volume.min()
    v_max = volume.max()
    if v_max > v_min:
        volume = (volume - v_min) / (v_max - v_min)
    else:
        volume = np.zeros_like(volume)

    return volume


class PreprocessStep(PipelineStep):
    """Build normalised numpy volumes from raw DICOM series."""

    name: str = "preprocess"

    def run(self, context: PipelineContext) -> PipelineContext:
        for series in context.dicom_series:
            context.volumes[series.description] = _build_volume(series)

        # Detect anatomy from the first series description
        if context.dicom_series:
            first_desc = context.dicom_series[0].description
            context.detected_anatomy = detect_anatomy(first_desc)

        # Detect plane for every series
        for series in context.dicom_series:
            context.detected_planes[series.description] = detect_plane(series.description)

        return context
