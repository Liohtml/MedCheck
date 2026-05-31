import numpy as np
from pydicom.dataset import Dataset

from medcheck.core.context import DicomSeries, PipelineContext
from medcheck.pipeline.preprocess import PreprocessStep, detect_anatomy, detect_plane


def _make_slice(rows=64, cols=64, series_desc="pd_tse_fs_sag_3mm", instance_num=1, slice_loc=0.0):
    ds = Dataset()
    ds.SeriesDescription = series_desc
    ds.InstanceNumber = instance_num
    ds.SliceLocation = slice_loc
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    pixel_data = np.random.randint(0, 1000, (rows, cols), dtype=np.uint16)
    ds.PixelData = pixel_data.tobytes()
    return ds


def test_preprocess_creates_volumes():
    slices = [_make_slice(instance_num=i, slice_loc=float(i)) for i in range(5)]
    series = DicomSeries(description="pd_sag", series_number=1, modality="MR", slices=slices)
    ctx = PipelineContext(dicom_series=[series])

    step = PreprocessStep()
    result = step.run(ctx)

    assert "pd_sag" in result.volumes
    vol = result.volumes["pd_sag"]
    assert vol.shape == (5, 64, 64)
    assert vol.min() >= 0.0
    assert vol.max() <= 1.0


def test_preprocess_sorts_by_slice_location():
    slices = [_make_slice(instance_num=i, slice_loc=float(5 - i)) for i in range(5)]
    series = DicomSeries(description="test", series_number=1, modality="MR", slices=slices)
    ctx = PipelineContext(dicom_series=[series])

    step = PreprocessStep()
    result = step.run(ctx)
    assert result.volumes["test"].shape[0] == 5


def test_detect_anatomy_knee():
    assert detect_anatomy("pd_tse_fs_sag_3mm") == "knee"
    assert detect_anatomy("Gelenke^Knie") == "knee"


def test_detect_anatomy_shoulder():
    assert detect_anatomy("shoulder_pd_cor") == "shoulder"


def test_detect_anatomy_spine():
    assert detect_anatomy("lumbar_spine_t2_sag") == "spine"


def test_detect_anatomy_hip():
    assert detect_anatomy("hip_pd_fs_cor") == "hip"
    assert detect_anatomy("Hüfte links") == "hip"


def test_detect_anatomy_ankle():
    assert detect_anatomy("ankle_t1_sag") == "ankle"
    assert detect_anatomy("Sprunggelenk rechts") == "ankle"
    assert detect_anatomy("foot_pd_fs") == "ankle"


def test_detect_anatomy_wrist():
    assert detect_anatomy("wrist_pd_cor") == "wrist"
    assert detect_anatomy("Handgelenk T2") == "wrist"


def test_detect_anatomy_unknown():
    assert detect_anatomy("unknown_sequence") == "unknown"


def test_detect_plane():
    assert detect_plane("pd_tse_fs_sag_3mm") == "sagittal"
    assert detect_plane("t1_se_cor_3mm") == "coronal"
    assert detect_plane("pd_tse_fs_tra_3mm") == "axial"
    assert detect_plane("pd_tse_fs_axi_3mm") == "axial"
    assert detect_plane("unknown") == "unknown"


def test_preprocess_step_name():
    assert PreprocessStep().name == "preprocess"
