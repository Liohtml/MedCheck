from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from medcheck.providers.local import LocalProvider


def _create_test_dicom(path: Path, series_desc: str = "test_series", series_num: int = 1) -> None:
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


def test_local_provider_loads_dicom_dir(tmp_path: Path):
    series_dir = tmp_path / "series1"
    series_dir.mkdir()
    _create_test_dicom(series_dir / "slice1.dcm", "sag_pd", 1)
    _create_test_dicom(series_dir / "slice2.dcm", "sag_pd", 1)
    provider = LocalProvider()
    result = provider.fetch(str(tmp_path), {})
    assert len(result) >= 1
    assert result[0].description == "sag_pd"
    assert len(result[0].slices) == 2


def test_local_provider_multiple_series(tmp_path: Path):
    for desc, num in [("sag_pd", 1), ("cor_t1", 2)]:
        d = tmp_path / f"series_{num}"
        d.mkdir()
        _create_test_dicom(d / "slice.dcm", desc, num)
    provider = LocalProvider()
    result = provider.fetch(str(tmp_path), {})
    assert len(result) == 2
    assert result[0].series_number < result[1].series_number


def test_local_provider_properties():
    provider = LocalProvider()
    assert provider.name == "local"
    assert provider.url_patterns == []
    assert provider.authenticate({}) is True


def test_local_provider_invalid_path():
    import pytest

    provider = LocalProvider()
    with pytest.raises(ValueError, match="must be a directory or ZIP"):
        provider.fetch("/nonexistent/path.txt", {})
