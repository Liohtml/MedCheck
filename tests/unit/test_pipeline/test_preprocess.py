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


def test_preprocess_heterogeneous_slice_shapes_keeps_dominant_group():
    slices = [_make_slice(instance_num=i, slice_loc=float(i)) for i in range(4)]
    slices.append(_make_slice(rows=32, cols=32, instance_num=5, slice_loc=5.0))  # localizer-sized outlier
    series = DicomSeries(description="mixed", series_number=1, modality="MR", slices=slices)
    ctx = PipelineContext(dicom_series=[series])

    result = PreprocessStep().run(ctx)

    assert result.volumes["mixed"].shape == (4, 64, 64)


def test_preprocess_empty_series_is_skipped_with_limitation():
    empty = DicomSeries(description="empty", series_number=1, modality="MR", slices=[])
    good = DicomSeries(
        description="good",
        series_number=2,
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(3)],
    )
    ctx = PipelineContext(dicom_series=[empty, good])

    result = PreprocessStep().run(ctx)

    assert "empty" not in result.volumes
    assert "good" in result.volumes
    assert any("empty" in note for note in result.limitations)


def test_preprocess_bad_series_does_not_abort_study():
    bad_slice = Dataset()  # no Rows/Columns/PixelData at all
    bad = DicomSeries(description="broken", series_number=1, modality="MR", slices=[bad_slice])
    good = DicomSeries(
        description="good",
        series_number=2,
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(3)],
    )
    ctx = PipelineContext(dicom_series=[bad, good])

    result = PreprocessStep().run(ctx)

    assert "broken" not in result.volumes
    assert "good" in result.volumes
    assert any("broken" in note for note in result.limitations)


def test_preprocess_duplicate_descriptions_keep_all_series():
    s1 = DicomSeries(
        description="pd_sag",
        series_number=1,
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(3)],
    )
    s2 = DicomSeries(
        description="pd_sag",  # identical description — must not overwrite s1
        series_number=2,
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(4)],
    )
    ctx = PipelineContext(dicom_series=[s1, s2])

    result = PreprocessStep().run(ctx)

    assert len(result.volumes) == 2
    assert result.volumes["pd_sag"].shape[0] == 3
    assert result.volumes["pd_sag (2)"].shape[0] == 4
    assert set(result.detected_planes) == {"pd_sag", "pd_sag (2)"}


def test_preprocess_empty_descriptions_keep_all_series():
    s1 = DicomSeries(
        description="",
        series_number=4,
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(2)],
    )
    s2 = DicomSeries(
        description="",
        series_number=0,  # unset series number falls back to positional index
        modality="MR",
        slices=[_make_slice(instance_num=i, slice_loc=float(i)) for i in range(2)],
    )
    ctx = PipelineContext(dicom_series=[s1, s2])

    result = PreprocessStep().run(ctx)

    assert len(result.volumes) == 2
    assert "series-4" in result.volumes
    assert "series-2" in result.volumes
