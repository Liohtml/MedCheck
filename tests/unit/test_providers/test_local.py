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


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    import zipfile

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_scan_zip_rejects_traversal(tmp_path: Path):
    import pytest

    zip_path = tmp_path / "evil.zip"
    _write_zip(zip_path, {"../escape.dcm": b"x"})
    with pytest.raises(ValueError, match="Unsafe path"):
        LocalProvider().fetch(str(zip_path), {})


def test_scan_zip_rejects_symlink_members(tmp_path: Path):
    import zipfile

    import pytest

    zip_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16  # symlink mode
        zf.writestr(info, "../../etc")
    with pytest.raises(ValueError, match="symlink"):
        LocalProvider().fetch(str(zip_path), {})


def test_scan_zip_rejects_zip_bomb_ratio(tmp_path: Path):
    import pytest

    zip_path = tmp_path / "bomb.zip"
    _write_zip(zip_path, {"bomb.bin": b"\x00" * (50 * 1024 * 1024)})
    with pytest.raises(ValueError, match="compression ratio"):
        LocalProvider().fetch(str(zip_path), {})


def test_scan_zip_accepts_normal_archive(tmp_path: Path):
    dicom_dir = tmp_path / "dicom"
    dicom_dir.mkdir()
    _create_test_dicom(dicom_dir / "slice1.dcm", "sag_pd", 1)
    import zipfile

    zip_path = tmp_path / "study.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(dicom_dir / "slice1.dcm", "series/slice1.dcm")
    result = LocalProvider().fetch(str(zip_path), {})
    assert len(result) == 1


def test_uid_grouping_keeps_identical_descriptions_separate(tmp_path):
    study = generate_uid()
    for index in range(3):
        path = tmp_path / f"{index}.dcm"
        _create_test_dicom(path, "identical", 1)
        ds = pydicom.dcmread(path)
        ds.StudyInstanceUID = study if index < 2 else generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        ds.save_as(path)
    result = LocalProvider().fetch(str(tmp_path), {})
    assert len(result) == 3
    assert len({s.metadata["study_instance_uid"] for s in result}) == 2


def test_dicomdir_import_and_escape_rejection(tmp_path):
    from unittest.mock import patch

    import pytest

    image_path = tmp_path / "IMAGE001"
    _create_test_dicom(image_path)
    directory = tmp_path / "DICOMDIR"
    directory.touch()
    record = pydicom.Dataset()
    record.ReferencedFileID = ["IMAGE001"]
    index = pydicom.Dataset()
    index.DirectoryRecordSequence = [record]
    original = pydicom.dcmread

    def read(path, **kwargs):
        return index if Path(path) == directory else original(path, **kwargs)

    with patch("medcheck.providers.local.pydicom.dcmread", side_effect=read):
        assert len(LocalProvider().fetch(str(directory), {})) == 1
        record.ReferencedFileID = ["..", "SECRET"]
        with pytest.raises(ValueError, match="Unsafe"):
            LocalProvider().fetch(str(directory), {})


def test_single_dicom_does_not_import_sibling_files(tmp_path):
    first = tmp_path / "one.dcm"
    _create_test_dicom(first, "one")
    _create_test_dicom(tmp_path / "two.dcm", "two")
    result = LocalProvider().fetch(str(first), {})
    assert len(result) == 1
    assert result[0].description == "one"


def test_input_quota_applies_to_single_file_and_aggregate(tmp_path, monkeypatch):
    import pytest

    first, second = tmp_path / "one.dcm", tmp_path / "two.dcm"
    _create_test_dicom(first)
    _create_test_dicom(second)
    monkeypatch.setenv("MEDCHECK_MAX_DICOM_BYTES", str(first.stat().st_size + 1))
    assert LocalProvider().fetch(str(first), {})
    with pytest.raises(ValueError, match="byte limit"):
        LocalProvider().fetch(str(tmp_path), {})
    monkeypatch.setenv("MEDCHECK_MAX_DICOM_BYTES", "1")
    with pytest.raises(ValueError, match="byte limit"):
        LocalProvider().fetch(str(first), {})


def test_zip_uncompressed_quota_applied_before_extraction(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv("MEDCHECK_MAX_DICOM_BYTES", "10")
    archive = tmp_path / "large.zip"
    _write_zip(archive, {"image.dcm": b"123456789012"})
    with pytest.raises(ValueError, match="uncompressed size"):
        LocalProvider().fetch(str(archive), {})
