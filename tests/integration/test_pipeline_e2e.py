"""End-to-end pipeline integration tests (no network, no optional ML deps).

Runs the real WorkflowEngine over synthetic DICOM data through the
ingest -> preprocess -> report steps and checks the generated artefacts.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from medcheck.core.context import PipelineContext
from medcheck.core.workflow import StepRegistry, WorkflowEngine
from medcheck.pipeline.ingest import IngestStep
from medcheck.pipeline.preprocess import PreprocessStep
from medcheck.pipeline.report import ReportStep

_STEPS = ["ingest", "preprocess", "report"]


def _create_test_dicom(path: Path, series_desc: str, series_num: int, instance: int) -> None:
    file_meta = pydicom.Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.PatientName = "Integration^Patient"
    ds.PatientID = "INT-4711"
    ds.PatientBirthDate = "19800101"
    ds.PatientSex = "F"
    ds.StudyDate = "20260601"
    ds.StudyDescription = "Knee MRI"
    ds.InstitutionName = "Integration Hospital"
    ds.Manufacturer = "SIEMENS"
    ds.ManufacturerModelName = "Avanto"
    ds.MagneticFieldStrength = "1.5"
    ds.Modality = "MR"
    ds.SeriesDescription = series_desc
    ds.SeriesNumber = series_num
    ds.InstanceNumber = instance
    ds.Rows = 32
    ds.Columns = 32
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.random.randint(0, 1000, (32, 32), dtype=np.uint16).tobytes()
    ds.save_as(str(path))


@pytest.fixture()
def dicom_study(tmp_path: Path) -> Path:
    study_dir = tmp_path / "study"
    study_dir.mkdir()
    for series, num in (("pd_sag_knee", 1), ("t1_cor_knee", 2)):
        series_dir = study_dir / series
        series_dir.mkdir()
        for i in range(1, 4):
            _create_test_dicom(series_dir / f"slice{i}.dcm", series, num, i)
    return study_dir


def _engine() -> WorkflowEngine:
    registry = StepRegistry()
    registry.register("ingest", IngestStep)
    registry.register("preprocess", PreprocessStep)
    registry.register("report", ReportStep)
    return WorkflowEngine(registry)


def _base_ctx(source: Path, output_dir: Path) -> PipelineContext:
    ctx = PipelineContext()
    ctx.source = str(source)
    ctx.report_format = "json"
    ctx.output_dir = str(output_dir)
    return ctx


def test_pipeline_directory_to_json_report(dicom_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    ctx = _engine().run(steps=_STEPS, context=_base_ctx(dicom_study, out))

    assert len(ctx.dicom_series) == 2
    assert ctx.patient.patient_id == "INT-4711"
    assert ctx.detected_anatomy == "knee"
    assert ctx.report_path.endswith(".json")

    data = json.loads(Path(ctx.report_path).read_text())
    assert data["patient"]["name"] == "Integration^Patient"
    assert data["study"]["institution"] == "Integration Hospital"
    assert data["detected_anatomy"] == "knee"


def test_pipeline_zip_source(dicom_study: Path, tmp_path: Path) -> None:
    zip_path = tmp_path / "study.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in sorted(dicom_study.rglob("*.dcm")):
            zf.write(f, f.relative_to(dicom_study))

    out = tmp_path / "out"
    ctx = _engine().run(steps=_STEPS, context=_base_ctx(zip_path, out))
    assert len(ctx.dicom_series) == 2
    assert Path(ctx.report_path).exists()


def test_pipeline_deidentified_report(dicom_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    base = _base_ctx(dicom_study, out)
    base.deidentify = True
    ctx = _engine().run(steps=_STEPS, context=base)

    raw = Path(ctx.report_path).read_text()
    assert "Integration^Patient" not in raw
    assert "INT-4711" not in raw
    assert "19800101" not in raw
    data = json.loads(raw)
    assert data["deidentified"] is True


def test_pipeline_html_report(dicom_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    base = _base_ctx(dicom_study, out)
    base.report_format = "html"
    base.report_language = "de"
    ctx = _engine().run(steps=_STEPS, context=base)
    assert ctx.report_path.endswith(".html")
    html_text = Path(ctx.report_path).read_text()
    assert 'lang="de"' in html_text
