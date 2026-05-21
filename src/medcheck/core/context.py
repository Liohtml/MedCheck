from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PatientInfo:
    name: str = ""
    patient_id: str = ""
    birth_date: str = ""
    sex: str = ""
    age: str = ""


@dataclass
class StudyInfo:
    date: str = ""
    description: str = ""
    institution: str = ""
    manufacturer: str = ""
    model_name: str = ""
    field_strength: str = ""


@dataclass
class DicomSeries:
    description: str = ""
    plane: str = ""
    modality: str = ""
    series_number: int = 0
    slices: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalStats:
    mean_intensity: list[float] = field(default_factory=list)
    max_intensity: list[float] = field(default_factory=list)
    high_signal_ratio: list[float] = field(default_factory=list)
    high_signal_slices: list[int] = field(default_factory=list)


@dataclass
class StructureFinding:
    name: str = ""
    status: str = ""
    findings: str = ""
    confidence: float = 0.0
    slices_evaluated: int = 0
    secondary_signs: list[str] = field(default_factory=list)


@dataclass
class ClinicalContext:
    symptoms: str = ""
    trauma: str = ""
    trauma_date: str = ""
    suspected_diagnosis: str = ""
    patient_age: int = 0
    patient_sex: str = ""
    anatomy: str = ""


@dataclass
class PipelineContext:
    dicom_series: list[DicomSeries] = field(default_factory=list)
    patient: PatientInfo = field(default_factory=PatientInfo)
    # Ingest config
    source: str = ""
    provider_name: str = "local"
    credentials: dict[str, str] = field(default_factory=dict)
    study: StudyInfo = field(default_factory=StudyInfo)
    volumes: dict[str, Any] = field(default_factory=dict)
    detected_anatomy: str | None = None
    detected_planes: dict[str, Any] = field(default_factory=dict)
    clinical_context: ClinicalContext | None = None
    anomaly_scores: dict[str, Any] = field(default_factory=dict)
    top_slices: dict[str, Any] = field(default_factory=dict)
    signal_analysis: dict[str, Any] = field(default_factory=dict)
    annotated_images: dict[str, Any] = field(default_factory=dict)
    findings: list[StructureFinding] = field(default_factory=list)
    overall_impression: str = ""
    clinical_correlation: str = ""
    limitations: list[str] = field(default_factory=list)
    report_path: str = ""
    report_format: str = "json"
    report_language: str = "en"
    output_dir: str = ""
    step_config: dict[str, Any] = field(default_factory=dict)
