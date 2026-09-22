"""Conservative in-memory DICOM de-identification and explicit pixel review.

Source files are never modified. This is a metadata allow-list, not a claim of
certified anonymization: burned-in text and recognizable anatomy need review.
"""

from __future__ import annotations

import copy
import importlib
import re
import secrets
from dataclasses import fields
from numbers import Integral
from typing import Any

import numpy as np
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

from medcheck.core.context import ClinicalContext, PatientInfo, PipelineContext, StudyInfo
from medcheck.core.step import PipelineStep

# Retain only image decoding, acquisition geometry and non-free-text identifiers.
_KEEP = frozenset(
    "SOPClassUID SOPInstanceUID StudyInstanceUID SeriesInstanceUID FrameOfReferenceUID "
    "Modality SeriesNumber InstanceNumber Rows Columns SamplesPerPixel PhotometricInterpretation "
    "PlanarConfiguration NumberOfFrames BitsAllocated BitsStored HighBit PixelRepresentation "
    "PixelData FloatPixelData DoubleFloatPixelData PixelSpacing SliceThickness SpacingBetweenSlices "
    "ImagePositionPatient ImageOrientationPatient SliceLocation RescaleIntercept RescaleSlope "
    "RescaleType ModalityLUTSequence LUTDescriptor LUTData WindowCenter WindowWidth VOILUTFunction BurnedInAnnotation "
    "SharedFunctionalGroupsSequence PerFrameFunctionalGroupsSequence "
    "PixelMeasuresSequence PlanePositionSequence PlaneOrientationSequence PixelValueTransformationSequence "
    "FrameVOILUTSequence FrameContentSequence DimensionIndexValues InStackPositionNumber "
    "TemporalPositionIndex StackID ImagePositionVolume ImageOrientationVolume".split()
)


def _scrub_dataset(ds: Dataset, uid_map: dict[str, str]) -> None:
    # pydicom datasets support deletion during iteration over a list snapshot.
    for element in list(ds):
        if element.keyword not in _KEEP:
            del ds[element.tag]
        elif element.VR == "SQ":
            for item in element.value:
                _scrub_dataset(item, uid_map)
        elif element.VR == "UI" and element.keyword != "SOPClassUID":
            original = str(element.value)
            element.value = uid_map.setdefault(original, generate_uid())


def redact_known_identifiers(text: str, identifiers: list[str]) -> str:
    variants = set(filter(None, identifiers))
    for identifier in list(variants):
        if "^" in identifier:
            parts = [part for part in identifier.split("^") if part]
            variants.update([" ".join(parts), " ".join(reversed(parts)), *[p for p in parts if len(p) > 1]])
    for value in sorted(variants, key=len, reverse=True):
        text = re.sub(re.escape(value), "[redacted]", text, flags=re.IGNORECASE)
    return text


def _preserve_anatomy_hint(context: PipelineContext) -> None:
    from medcheck.pipeline.preprocess import detect_anatomy

    anatomy = next(
        (hint for series in context.dicom_series if (hint := detect_anatomy(series.description)) != "unknown"), ""
    )
    if anatomy:
        if context.clinical_context is None:
            context.clinical_context = ClinicalContext(anatomy=anatomy)
        elif not context.clinical_context.anatomy:
            context.clinical_context.anatomy = anatomy


def _scrub_file_meta(ds: Dataset) -> None:
    if getattr(ds, "file_meta", None):
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID if hasattr(ds, "SOPInstanceUID") else generate_uid()
        for tag in list(ds.file_meta.keys()):
            if tag.group != 2 or tag.element not in {0, 1, 2, 3, 16, 18}:
                del ds.file_meta[tag]


def _redact_value(value: Any, identifiers: list[str], aliases: dict[str, str] | None = None) -> Any:
    """Scrub nested report values without retaining the identifier list anywhere."""
    if isinstance(value, str):
        return (aliases or {}).get(value, redact_known_identifiers(value, identifiers))
    if isinstance(value, dict):
        return {key: _redact_value(item, identifiers, aliases) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, identifiers, aliases) for item in value]
    return value


def _redact_existing_results(context: PipelineContext, identifiers: list[str]) -> None:
    keyed_fields = (
        "volumes",
        "detected_planes",
        "anomaly_scores",
        "top_slices",
        "signal_analysis",
        "annotated_images",
        "slice_references",
        "quality_checks",
        "redactions",
    )
    aliases: dict[str, str] = {}
    used: set[str] = set()
    for attr in keyed_fields:
        for name in getattr(context, attr):
            if name in aliases:
                continue
            base = redact_known_identifiers(name, identifiers)
            label, suffix = base, 2
            while label in used:
                label = f"{base} ({suffix})"
                suffix += 1
            used.add(label)
            aliases[name] = label
    for finding in context.findings:
        for finding_field in fields(finding):
            setattr(
                finding, finding_field.name, _redact_value(getattr(finding, finding_field.name), identifiers, aliases)
            )
    for attr in (
        "overall_impression",
        "clinical_correlation",
        "limitations",
        "review_history",
        "reconciliation",
        "analysis_provenance",
    ):
        setattr(context, attr, _redact_value(getattr(context, attr), identifiers, aliases))
    # Series labels can be free text. Keep dictionary keys and image references aligned.
    for attr in keyed_fields:
        current = getattr(context, attr)
        setattr(
            context, attr, {aliases[key]: _redact_value(value, identifiers, aliases) for key, value in current.items()}
        )


class DeidentifyStep(PipelineStep):
    name = "deidentify"

    def run(self, context: PipelineContext) -> PipelineContext:
        if not context.deidentify:
            return context
        identifiers = [context.patient.name, context.patient.patient_id, context.patient.birth_date]
        # Random per-run pseudonyms cannot be reversed by guessing common patient IDs.
        pseudo = secrets.token_hex(8)
        _preserve_anatomy_hint(context)
        context.dicom_series = copy.deepcopy(context.dicom_series)
        uid_map: dict[str, str] = {}
        for index, series in enumerate(context.dicom_series):
            for ds in series.slices:
                identifiers.extend(
                    str(getattr(ds, attr, "")) for attr in ("PatientName", "PatientID", "PatientBirthDate")
                )
                _scrub_dataset(ds, uid_map)
                ds.PatientIdentityRemoved = "YES"
                ds.DeidentificationMethod = "MedCheck metadata allow-list; pixels require independent review"
                ds.PatientName = f"Subject^{pseudo}"
                ds.PatientID = pseudo
                _scrub_file_meta(ds)
            # Descriptions are free text and can carry identifiers: replace, do not guess.
            series.description = f"Series {index + 1}"
            series.metadata = {
                key: uid_map.setdefault(str(value), generate_uid()) if value else ""
                for key, value in series.metadata.items()
                if key in {"study_instance_uid", "series_instance_uid"}
            }
        if context.clinical_context:
            for attr in ("symptoms", "trauma", "trauma_date", "suspected_diagnosis", "anatomy"):
                value = getattr(context.clinical_context, attr)
                setattr(context.clinical_context, attr, redact_known_identifiers(value, identifiers))
        context.official_report = redact_known_identifiers(context.official_report, identifiers)
        _redact_existing_results(context, identifiers)
        context.patient = PatientInfo(name=f"Subject^{pseudo}", patient_id=pseudo)
        context.study = StudyInfo()
        context.study_instance_uid = uid_map.get(context.study_instance_uid, "")
        context.analysis_provenance["deidentification"] = {
            "metadata": "allow-list",
            "metadata_deidentified": True,
            "pixels_reviewed": context.pixels_reviewed,
            "free_text_anonymization_guaranteed": False,
            "certified_anonymization": False,
        }
        context.limitations.append(
            "Metadata de-identification does not guarantee anonymous pixels or free text. "
            "Embedded text and recognizable anatomy require independent review."
        )
        return context


def _validated_rectangle(rect: list[int], shape: tuple[int, ...]) -> tuple[int, int, int, int]:
    if len(rect) != 4 or any(not isinstance(value, Integral) or isinstance(value, bool) for value in rect):
        raise ValueError("Redaction must contain integer x, y, width, height")
    x, y, width, height = (int(value) for value in rect)
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > shape[2] or y + height > shape[1]:
        raise ValueError("Redaction rectangle is outside the image")
    return x, y, width, height


def _ocr_rectangles(slice_array: np.ndarray) -> list[list[int]]:
    """Detect text locally. No OCR text is retained or sent to another service."""
    try:
        pytesseract = importlib.import_module("pytesseract")
    except ImportError as exc:
        raise RuntimeError("OCR requires the privacy extra and a local Tesseract installation") from exc
    image = (np.clip(slice_array, 0, 1) * 255).astype(np.uint8)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, timeout=15)
    rectangles = []
    for index, text in enumerate(data["text"]):
        if not str(text).strip():
            continue
        # Pad the bounding box; OCR can miss the first/last pixels of a glyph.
        x = max(0, int(data["left"][index]) - 2)
        y = max(0, int(data["top"][index]) - 2)
        right = min(image.shape[1], int(data["left"][index]) + int(data["width"][index]) + 2)
        bottom = min(image.shape[0], int(data["top"][index]) + int(data["height"][index]) + 2)
        if right > x and bottom > y:
            rectangles.append([x, y, right - x, bottom - y])
    return rectangles


def apply_pixel_redactions(context: PipelineContext) -> None:
    """Validate every mask before changing pixels; optional local OCR is only an aid."""
    validated: dict[str, list[tuple[int, int, int, int]]] = {}
    for series, rectangles in context.redactions.items():
        if series not in context.volumes:
            raise ValueError("Redaction refers to an unknown series")
        validated[series] = [_validated_rectangle(rect, context.volumes[series].shape) for rect in rectangles]
    ocr_enabled = context.step_config.get("ocr", False)
    if not isinstance(ocr_enabled, bool):
        raise ValueError("OCR must be a boolean")
    # Copy volumes so consumers holding original arrays keep untouched pixel data.
    volumes = {name: volume.copy() for name, volume in context.volumes.items()}
    detected: dict[str, list[dict[str, Any]]] = {}
    for name, volume in volumes.items():
        for x, y, width, height in validated.get(name, []):
            volume[:, y : y + height, x : x + width] = 0
        if ocr_enabled:
            detected[name] = []
            for index, slice_array in enumerate(volume):
                for rectangle in _ocr_rectangles(slice_array):
                    x, y, width, height = _validated_rectangle(rectangle, volume.shape)
                    volume[index, y : y + height, x : x + width] = 0
                    detected[name].append({"slice_index": index, "rectangle": rectangle})
    context.volumes = volumes
    context.analysis_provenance["pixel_redactions"] = copy.deepcopy(context.redactions)
    if ocr_enabled:
        context.analysis_provenance["ocr_redactions"] = detected
        context.limitations.append("OCR masking may miss embedded text; independent pixel review remains required.")
