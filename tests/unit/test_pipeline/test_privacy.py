from unittest.mock import patch

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from medcheck.core.context import ClinicalContext, DicomSeries, PatientInfo, PipelineContext
from medcheck.pipeline.privacy import DeidentifyStep, apply_pixel_redactions, redact_known_identifiers


def make_dataset(study_uid, series_uid):
    ds = Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "ID123"
    ds.PatientBirthDate = "19800102"
    ds.SeriesDescription = "Jane Doe knee"
    ds.add_new((0x0011, 0x0010), "LO", "SECRET")
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.ImplementationVersionName = "PRIVATE_NAME"
    nested = Dataset()
    nested.PatientName = "Nested^Secret"
    nested.ImagePositionPatient = [0, 0, 1]
    ds.PlanePositionSequence = Sequence([nested])
    ds.Rows = 2
    ds.Columns = 2
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.arange(4, dtype=np.uint16).tobytes()
    return ds


def test_deidentify_copies_sources_scrubs_nested_tags_and_preserves_uid_relations():
    study_uid, series_uid = generate_uid(), generate_uid()
    original = [make_dataset(study_uid, series_uid) for _ in range(2)]
    series = DicomSeries(
        description="knee",
        slices=original,
        metadata={"study_instance_uid": study_uid, "series_instance_uid": series_uid},
    )
    ctx = PipelineContext(
        deidentify=True,
        dicom_series=[series],
        study_instance_uid=study_uid,
        patient=PatientInfo(name="Doe^Jane", patient_id="ID123"),
        official_report="Jane Doe (ID123), born 19800102",
        clinical_context=ClinicalContext(),
    )
    DeidentifyStep().run(ctx)
    cleaned = ctx.dicom_series[0].slices
    assert str(original[0].PatientName) == "Doe^Jane"
    assert series.description == "knee"
    assert "PatientName" in original[0].PlanePositionSequence[0]
    assert all(ds.StudyInstanceUID != study_uid for ds in cleaned)
    assert cleaned[0].StudyInstanceUID == cleaned[1].StudyInstanceUID
    assert cleaned[0].SeriesInstanceUID == cleaned[1].SeriesInstanceUID
    assert cleaned[0].SOPInstanceUID != cleaned[1].SOPInstanceUID
    assert cleaned[0].file_meta.MediaStorageSOPInstanceUID == cleaned[0].SOPInstanceUID
    assert cleaned[0].file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert "ImplementationVersionName" not in cleaned[0].file_meta
    assert not any(element.tag.is_private for element in cleaned[0])
    assert "PatientName" not in cleaned[0].PlanePositionSequence[0]
    assert "ImagePositionPatient" in cleaned[0].PlanePositionSequence[0]
    assert ctx.study_instance_uid == cleaned[0].StudyInstanceUID
    assert ctx.dicom_series[0].metadata["series_instance_uid"] == cleaned[0].SeriesInstanceUID
    assert np.array_equal(cleaned[0].pixel_array, original[0].pixel_array)
    assert ctx.clinical_context.anatomy == "knee"
    assert "Jane" not in ctx.official_report and "ID123" not in ctx.official_report
    assert "19800102" not in ctx.official_report
    assert ctx.analysis_provenance["deidentification"]["pixels_reviewed"] is False
    assert any("does not guarantee" in note for note in ctx.limitations)


def test_deidentify_preserves_explicit_anatomy_and_disabled_is_noop():
    ctx = PipelineContext(
        dicom_series=[DicomSeries(description="knee")], clinical_context=ClinicalContext(anatomy="shoulder")
    )
    assert DeidentifyStep().run(ctx) is ctx
    assert ctx.dicom_series[0].description == "knee"
    ctx.deidentify = True
    DeidentifyStep().run(ctx)
    assert ctx.clinical_context.anatomy == "shoulder"


def test_known_identifier_redaction_case_and_dicom_name_variants():
    assert redact_known_identifiers("Jane Doe, DOE^JANE id123", ["Doe^Jane", "ID123"]) == (
        "[redacted], [redacted] [redacted]"
    )


@pytest.mark.parametrize(
    "rectangle", [[-1, 0, 1, 1], [0, 0, 0, 1], [3, 0, 2, 1], [0, 0, 1], [0.5, 0, 1, 1], [True, 0, 1, 1]]
)
def test_invalid_masks_fail_before_any_pixels_change(rectangle):
    pixels = np.ones((2, 4, 4))
    ctx = PipelineContext(volumes={"s": pixels}, redactions={"s": [[0, 0, 1, 1], rectangle]})
    with pytest.raises(ValueError, match="Redaction"):
        apply_pixel_redactions(ctx)
    assert np.all(ctx.volumes["s"] == 1)


def test_explicit_masks_copy_original_pixels_and_ocr_is_opt_in():
    pixels = np.ones((2, 4, 4))
    ctx = PipelineContext(volumes={"s": pixels}, redactions={"s": [[1, 1, 2, 1]]})
    with patch("medcheck.pipeline.privacy._ocr_rectangles") as ocr:
        apply_pixel_redactions(ctx)
    ocr.assert_not_called()
    assert np.all(pixels == 1)
    assert np.all(ctx.volumes["s"][:, 1, 1:3] == 0)
    assert np.all(ctx.volumes["s"][:, 0, :] == 1)
    assert not ctx.pixels_reviewed


def test_ocr_masks_each_slice_and_does_not_mark_pixels_reviewed():
    ctx = PipelineContext(volumes={"s": np.ones((2, 4, 4))}, step_config={"ocr": True})
    with patch("medcheck.pipeline.privacy._ocr_rectangles", return_value=[[0, 0, 2, 1]]) as ocr:
        apply_pixel_redactions(ctx)
    assert ocr.call_count == 2
    assert np.all(ctx.volumes["s"][:, 0, :2] == 0)
    assert len(ctx.analysis_provenance["ocr_redactions"]["s"]) == 2
    assert not ctx.pixels_reviewed
    assert any("may miss" in note for note in ctx.limitations)


def test_ocr_failure_does_not_commit_partial_masks():
    ctx = PipelineContext(volumes={"s": np.ones((2, 4, 4))}, step_config={"ocr": True})
    with patch("medcheck.pipeline.privacy._ocr_rectangles", side_effect=[[[0, 0, 1, 1]], RuntimeError("timeout")]):
        with pytest.raises(RuntimeError, match="timeout"):
            apply_pixel_redactions(ctx)
    assert np.all(ctx.volumes["s"] == 1)


def test_existing_report_text_and_nested_review_history_redact_known_identifiers():
    import json

    from medcheck.core.context import StructureFinding
    from medcheck.pipeline.report import generate_json_report

    ctx = PipelineContext(
        deidentify=True,
        patient=PatientInfo(name="Doe^Jane", patient_id="ID123", birth_date="19800102"),
        findings=[
            StructureFinding(
                name="ACL",
                findings="Jane Doe ID123 reports pain",
                secondary_signs=["ID123"],
                image_references=[{"series_name": "ID123 knee", "slice_index": 0}],
            )
        ],
        overall_impression="ID123: pain",
        clinical_correlation="Doe^Jane born 19800102",
        limitations=["Patient ID123"],
        review_history=[{"before": {"findings": "Jane Doe"}, "note": "ID123"}],
        reconciliation={"reference_report": "19800102 ID123", "comparisons": [{"reference_passages": ["Jane Doe"]}]},
        analysis_provenance={"operator_note": "ID123"},
        volumes={"ID123 knee": np.ones((1, 2, 2))},
        quality_checks={"ID123 knee": ["Jane Doe"]},
    )
    DeidentifyStep().run(ctx)
    report = generate_json_report(ctx)
    assert all(identifier not in report for identifier in ("Jane", "Doe", "ID123", "19800102"))
    parsed = json.loads(report)
    reference_name = parsed["findings"][0]["image_references"][0]["series_name"]
    assert reference_name in ctx.volumes
    assert ctx.analysis_provenance["deidentification"]["free_text_anonymization_guaranteed"] is False


def test_redacted_series_names_do_not_collide_or_break_finding_references():
    from medcheck.core.context import StructureFinding

    ctx = PipelineContext(
        deidentify=True,
        patient=PatientInfo(name="Doe^Jane", patient_id="ID123"),
        volumes={"Jane knee": np.ones((1, 2, 2)), "ID123 knee": np.zeros((1, 2, 2))},
        findings=[StructureFinding(name="ACL", image_references=[{"series_name": "ID123 knee", "slice_index": 0}])],
    )
    DeidentifyStep().run(ctx)
    assert len(ctx.volumes) == 2
    assert list(ctx.volumes) == ["[redacted] knee", "[redacted] knee (2)"]
    assert ctx.findings[0].image_references[0]["series_name"] == "[redacted] knee (2)"
