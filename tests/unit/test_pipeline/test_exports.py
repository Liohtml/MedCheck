import base64
import io
import json

import pydicom
from pydicom.uid import BasicTextSRStorage, ExplicitVRLittleEndian

from medcheck.core.context import PatientInfo, PipelineContext, StructureFinding, StudyInfo
from medcheck.pipeline.exports import DISCLAIMER, dicom_sr, fhir_report
from medcheck.pipeline.report import generate_json_report


def _context(deidentify=False):
    return PipelineContext(
        patient=PatientInfo(name="Example^Person", patient_id="patient-secret-001", birth_date="19800101", sex="F"),
        study=StudyInfo(date="20250101"),
        study_instance_uid="1.2.826.0.1.3680043.8.498.123",
        deidentify=deidentify,
        findings=[
            StructureFinding(name="ACL", status="normal", findings="No focal change.", review_status="confirmed")
        ],
        overall_impression="Research finding only.",
        limitations=["Limited image sample."],
    )


def test_fhir_contained_references_resolve_and_remain_preliminary():
    report = json.loads(generate_json_report(_context()))
    result = fhir_report(report)
    assert result["resourceType"] == "DiagnosticReport"
    assert result["status"] == "preliminary"
    contained = {f"#{item['id']}": item for item in result["contained"]}
    assert len(contained) == len(report["findings"])
    for reference in result["result"]:
        observation = contained[reference["reference"]]
        assert observation["resourceType"] == "Observation"
        assert observation["status"] == "preliminary"
        assert "confirmed" in observation["note"][0]["text"]
    assert DISCLAIMER in result["conclusion"]
    assert json.loads(base64.b64decode(result["presentedForm"][0]["data"])) == report


def test_empty_fhir_report_has_no_dangling_references():
    context = _context()
    context.findings = []
    result = fhir_report(json.loads(generate_json_report(context)))
    assert not result.get("contained")
    assert not result.get("result")


def test_dicom_sr_readback_flags_and_content():
    context = _context()
    report = json.loads(generate_json_report(context))
    ds = pydicom.dcmread(io.BytesIO(dicom_sr(context, report)))
    assert ds.SOPClassUID == BasicTextSRStorage
    assert ds.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert ds.SOPInstanceUID == ds.file_meta.MediaStorageSOPInstanceUID
    assert ds.StudyInstanceUID == context.study_instance_uid
    assert ds.Modality == "SR"
    assert ds.CompletionFlag == "PARTIAL"
    assert ds.VerificationFlag == "UNVERIFIED"
    assert ds.PreliminaryFlag == "PRELIMINARY"
    assert ds.ValueType == "CONTAINER"
    texts = [item.TextValue for item in ds.ContentSequence]
    assert DISCLAIMER in texts
    assert "Limited image sample." in texts
    assert any("ACL" in text and "confirmed" in text for text in texts)


def test_exports_use_pseudonymized_patient_values():
    context = _context(deidentify=True)
    report = json.loads(generate_json_report(context))
    fhir = fhir_report(report)
    embedded = json.loads(base64.b64decode(fhir["presentedForm"][0]["data"]))
    ds = pydicom.dcmread(io.BytesIO(dicom_sr(context, report)))
    assert embedded["deidentified"]
    assert embedded["patient"]["patient_id"] != context.patient.patient_id
    assert ds.PatientID == embedded["patient"]["patient_id"]
    assert str(ds.PatientName) == embedded["patient"]["name"]
    assert ds.PatientBirthDate == ""
    assert context.patient.name not in json.dumps(fhir)
    assert context.patient.patient_id not in json.dumps(embedded)
    assert context.patient.patient_id not in str(ds)
