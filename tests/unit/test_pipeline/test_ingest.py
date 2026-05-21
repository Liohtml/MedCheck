from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from medcheck.core.context import PipelineContext
from medcheck.pipeline.ingest import IngestStep


def _create_test_dicom(path: Path, series_desc: str = "test", series_num: int = 1) -> None:
    file_meta = pydicom.Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.PatientName = "Test^Patient"
    ds.PatientID = "12345"
    ds.PatientBirthDate = "19970121"
    ds.PatientSex = "M"
    ds.StudyDate = "20260521"
    ds.StudyDescription = "Knee MRI"
    ds.InstitutionName = "Test Hospital"
    ds.Manufacturer = "SIEMENS"
    ds.ManufacturerModelName = "Symphony"
    ds.MagneticFieldStrength = "1.5"
    ds.Modality = "MR"
    ds.SeriesDescription = series_desc
    ds.SeriesNumber = series_num
    ds.InstanceNumber = 1
    ds.Rows = 64
    ds.Columns = 64
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.zeros((64, 64), dtype=np.uint16).tobytes()
    ds.save_as(str(path))


def test_ingest_step_loads_local_dicom(tmp_path: Path):
    d = tmp_path / "series"
    d.mkdir()
    _create_test_dicom(d / "s1.dcm", "pd_sag", 1)
    _create_test_dicom(d / "s2.dcm", "pd_sag", 1)

    ctx = PipelineContext()
    ctx.source = str(tmp_path)  # IngestStep should read this
    ctx.provider_name = "local"
    ctx.credentials = {}

    step = IngestStep()
    result = step.run(ctx)

    assert len(result.dicom_series) >= 1
    assert result.dicom_series[0].description == "pd_sag"
    assert result.patient.name == "Test^Patient"
    assert result.patient.birth_date == "19970121"
    assert result.study.date == "20260521"
    assert result.study.institution == "Test Hospital"


def test_ingest_step_name():
    assert IngestStep().name == "ingest"
