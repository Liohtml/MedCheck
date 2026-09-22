"""Preliminary FHIR R4 DiagnosticReport and DICOM Basic Text SR export.

References: https://hl7.org/fhir/R4/diagnosticreport.html and DICOM PS3.3 C.17.2.
Exports remain research drafts regardless of user review annotations.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from typing import Any

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import BasicTextSRStorage, ExplicitVRLittleEndian, generate_uid

from medcheck.core.context import PipelineContext

DISCLAIMER = "Research output, not a diagnosis. Unvalidated AI findings require independent qualified review."


def fhir_report(report: dict[str, Any]) -> dict[str, Any]:
    observations = []
    for index, finding in enumerate(report["findings"]):
        observations.append(
            {
                "resourceType": "Observation",
                "id": f"finding-{index}",
                "status": "preliminary",
                "code": {"text": finding["name"] or "Image observation"},
                "valueString": finding["findings"],
                "note": [{"text": f"Review: {finding.get('review_status', 'unreviewed')}. {DISCLAIMER}"}],
            }
        )
    result: dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",
        "code": {"text": "MedCheck research imaging analysis"},
        "issued": report["generated_at"],
        "conclusion": f"{report['overall_impression']}\n{DISCLAIMER}",
        "presentedForm": [
            {
                "contentType": "application/json",
                "title": "MedCheck research report",
                "data": base64.b64encode(json.dumps(report).encode()).decode(),
            }
        ],
    }
    if observations:
        result["contained"] = observations
        result["result"] = [{"reference": f"#{item['id']}"} for item in observations]
    return result


def _code(value: str, meaning: str, scheme: str = "DCM") -> Sequence:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return Sequence([item])


def dicom_sr(context: PipelineContext, report: dict[str, Any]) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = BasicTextSRStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(io.BytesIO(), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = report["patient"]["name"]
    ds.PatientID = report["patient"]["patient_id"]
    ds.PatientBirthDate = report["patient"]["birth_date"]
    ds.PatientSex = report["patient"]["sex"]
    ds.StudyInstanceUID = generate_uid() if report.get("deidentified") else context.study_instance_uid or generate_uid()
    if report.get("deidentified"):
        ds.PatientIdentityRemoved = "YES"
        ds.DeidentificationMethod = "Pseudonymous research report; source images not included"
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyDate = report["study"]["date"]
    ds.StudyTime = ""
    ds.ReferringPhysicianName = ""
    ds.StudyID = ""
    ds.AccessionNumber = ""
    ds.Modality = "SR"
    ds.SeriesNumber = 900
    ds.InstanceNumber = 1
    ds.Manufacturer = "MedCheck"
    ds.SeriesDescription = "Research analysis - unverified"
    ds.ReferencedPerformedProcedureStepSequence = Sequence([])
    ds.PerformedProcedureCodeSequence = Sequence([])
    now = datetime.now(timezone.utc)
    ds.ContentDate = now.strftime("%Y%m%d")
    ds.ContentTime = now.strftime("%H%M%S")
    ds.TimezoneOffsetFromUTC = "+0000"
    ds.CompletionFlag = "PARTIAL"
    ds.VerificationFlag = "UNVERIFIED"
    ds.PreliminaryFlag = "PRELIMINARY"
    ds.ValueType = "CONTAINER"
    ds.ContinuityOfContent = "SEPARATE"
    ds.ConceptNameCodeSequence = _code("126000", "Imaging Measurement Report")
    texts = [DISCLAIMER, report["overall_impression"], *report["limitations"]]
    texts += [
        f"{f['name']}: {f['findings']} (review: {f.get('review_status', 'unreviewed')})" for f in report["findings"]
    ]
    items = []
    for text in filter(None, texts):
        item = Dataset()
        item.RelationshipType = "CONTAINS"
        item.ValueType = "TEXT"
        item.ConceptNameCodeSequence = _code("121071", "Finding")
        item.TextValue = text
        items.append(item)
    ds.ContentSequence = Sequence(items)
    output = io.BytesIO()
    ds.save_as(output, enforce_file_format=True)
    return output.getvalue()
