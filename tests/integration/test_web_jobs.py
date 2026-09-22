"""Workbench API integration using synthetic pixels and no model or network calls."""

import io
import json
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import pydicom
import pytest
from fastapi.testclient import TestClient
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from medcheck.core.config import Settings
from medcheck.core.context import StructureFinding
from medcheck.web.app import create_app


def _dicom_bytes():
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = MRImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientName = "Synthetic^Only"
    ds.PatientID = "synthetic-patient-id"
    ds.StudyDate = "20250101"
    ds.SeriesDescription = "knee sagittal"
    ds.Modality = "MR"
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1
    ds.Rows = ds.Columns = 16
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, 0]
    ds.PixelSpacing = [1, 1]
    ds.SliceThickness = 1
    ds.PixelData = np.arange(256, dtype=np.uint16).tobytes()
    result = io.BytesIO()
    ds.save_as(result, enforce_file_format=True)
    return result.getvalue()


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDCHECK_RATE_LIMIT", "0")
    data = tmp_path / "data"
    data.mkdir()
    return Settings(data_root=str(data), state_dir=str(tmp_path / "state"), api_key=None)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client, zipped=False):
    data = _dicom_bytes()
    name = "synthetic.dcm"
    if zipped:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("scan/image.dcm", data)
        name, data = "synthetic.zip", output.getvalue()
    response = client.post("/api/upload", files={"file": (name, data, "application/octet-stream")})
    assert response.status_code == 200, response.text
    return response.json()["source"]


def _submit(client, source, **kwargs):
    response = client.post("/api/analyze", json={"source": source, **kwargs})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def _finished(client, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    pytest.fail(f"Analysis did not finish: {job}")


@pytest.mark.parametrize("zipped", [False, True])
def test_upload_inspect_analyze_view_export_delete(client, settings, zipped):
    source = _upload(client, zipped)
    inspection = client.post("/api/inspect", json={"source": source})
    assert inspection.status_code == 200, inspection.text
    study = inspection.json()["studies"][0]
    assert study["series"][0]["slices"] == 1
    job_id = _submit(client, source, study_uid=study["study_uid"])
    job = _finished(client, job_id)
    assert job["status"] == "completed", job
    assert job["progress"] == 100
    assert job["viewer_available"]
    assert "synthetic-patient-id" not in json.dumps(job["result"])
    image = client.get(f"/api/jobs/{job_id}/images/0/0")
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    assert client.get(f"/api/jobs/{job_id}/images/0/99").status_code == 404
    for fmt in ("json", "html", "pdf", "fhir", "dicom-sr"):
        report = client.get(f"/api/jobs/{job_id}/report", params={"format": fmt})
        assert report.status_code == 200, report.text[:200] if fmt != "dicom-sr" else report.status_code
        assert "attachment" in report.headers["content-disposition"]
        assert report.headers["cache-control"] == "no-store"
        if fmt == "pdf":
            assert report.content.startswith(b"%PDF")
        if fmt == "fhir":
            assert report.json()["status"] == "preliminary"
        if fmt == "dicom-sr":
            assert pydicom.dcmread(io.BytesIO(report.content)).VerificationFlag == "UNVERIFIED"
    assert client.get(f"/api/jobs/{job_id}/report?format=invalid").status_code == 422
    assert len(client.get("/api/jobs").json()) == 1
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert not (Path(settings.state_dir) / job_id).exists()
    assert client.delete(f"/api/uploads/{source.split(':')[1]}").status_code == 200
    assert not list((Path(settings.state_dir) / "uploads").iterdir())


def test_cancel_running_and_queued_jobs(client, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def block(self, context):
        started.set()
        assert release.wait(10), "test worker was not released"
        return context

    monkeypatch.setattr("medcheck.web.jobs.IngestStep.run", block)
    source = _upload(client)
    first = _submit(client, source)
    assert started.wait(5)
    second = _submit(client, source)
    try:
        assert client.delete(f"/api/jobs/{first}").status_code == 409
        assert client.get(f"/api/jobs/{first}/report").status_code == 409
        assert client.delete(f"/api/uploads/{source.split(':')[1]}").status_code == 409
        assert client.post(f"/api/jobs/{first}/cancel").json()["cancel_requested"]
        assert client.post(f"/api/jobs/{second}/cancel").json()["cancel_requested"]
    finally:
        release.set()
    assert _finished(client, first)["status"] == "cancelled"
    assert _finished(client, second)["status"] == "cancelled"
    assert client.delete(f"/api/jobs/{first}").status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/capabilities"),
        ("POST", "/api/upload"),
        ("POST", "/api/inspect"),
        ("POST", "/api/preview"),
        ("POST", "/api/analyze"),
        ("GET", "/api/jobs"),
        ("GET", "/api/jobs/missing"),
        ("POST", "/api/jobs/missing/cancel"),
        ("DELETE", "/api/jobs/missing"),
        ("PATCH", "/api/jobs/missing/findings/0"),
        ("GET", "/api/jobs/missing/images/0/0"),
        ("GET", "/api/jobs/missing/report"),
        ("DELETE", "/api/uploads/missing"),
    ],
)
def test_all_api_routes_require_auth(settings, method, path):
    settings.api_key = "secret"
    with TestClient(create_app(settings)) as client:
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/api/jobs", headers={"X-API-Key": "secret"}).status_code == 200


def test_source_traversal_and_symlink_rejected(client, settings, tmp_path):
    outside = tmp_path / "outside.dcm"
    outside.write_bytes(_dicom_bytes())
    sources = [str(outside), str(Path(settings.data_root) / ".." / "outside.dcm"), "upload:../outside"]
    link = Path(settings.data_root) / "link.dcm"
    try:
        link.symlink_to(outside)
        sources.extend([str(link), settings.data_root])
    except OSError:
        pass  # Windows may prohibit creating symlinks without developer mode.
    for source in sources:
        assert client.post("/api/inspect", json={"source": source}).status_code == 422
        assert client.post("/api/analyze", json={"source": source}).status_code == 422


def test_invalid_and_oversize_uploads_cleanup(client, settings):
    settings.max_upload_bytes = 10
    for name, data, status in [("a.dcm", b"x" * 11, 413), ("empty.dcm", b"", 422), ("script.py", b"x", 422)]:
        response = client.post("/api/upload", files={"file": (name, data)})
        assert response.status_code == status
    assert not list((Path(settings.state_dir) / "uploads").iterdir())


def test_failure_is_actionable_and_private(client, monkeypatch):
    def fail(self, context):
        raise RuntimeError("secret provider response containing patient info")

    monkeypatch.setattr("medcheck.web.jobs.IngestStep.run", fail)
    job = _finished(client, _submit(client, _upload(client)))
    assert job["status"] == "failed"
    assert "configuration" in job["error"]
    assert "secret" not in job["error"]
    assert not job["viewer_available"]


def test_review_audit_and_restart_durable_reports(settings, monkeypatch):
    def finding(self, context):
        context.findings = [StructureFinding(name="ACL", status="normal", findings="Original text")]
        return context

    monkeypatch.setattr("medcheck.web.jobs.ReconcileStep.run", finding)
    with TestClient(create_app(settings)) as client:
        job_id = _submit(client, _upload(client))
        assert _finished(client, job_id)["status"] == "completed"
        route = f"/api/jobs/{job_id}/findings/0"
        assert client.patch(route, json={"status": "edited"}).status_code == 422
        edited = client.patch(route, json={"status": "edited", "findings": "Corrected text", "note": "Reviewed"})
        assert edited.status_code == 200
        audit = edited.json()["review_history"][0]
        assert audit["before"]["findings"] == "Original text"
        assert audit["after"]["findings"] == "Corrected text"
        assert audit["note"] == "Reviewed"
        assert client.patch(f"/api/jobs/{job_id}/findings/99", json={"status": "confirmed"}).status_code == 422
    with TestClient(create_app(settings)) as restarted:
        job = restarted.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["viewer_available"]
        assert restarted.get(f"/api/jobs/{job_id}/images/0/0").status_code == 200
        report = restarted.get(f"/api/jobs/{job_id}/report").json()
        assert report["findings"][0]["findings"] == "Corrected text"
        assert report["review_history"][0] == audit
        assert restarted.get(f"/api/jobs/{job_id}/report?format=pdf").status_code == 200


def test_restart_marks_interrupted_job_failed(settings):
    folder = Path(settings.state_dir) / ("a" * 32)
    folder.mkdir(parents=True)
    (folder / "status.json").write_text(json.dumps({"id": folder.name, "status": "running"}))
    with TestClient(create_app(settings)) as client:
        job = client.get(f"/api/jobs/{folder.name}").json()
        assert job["status"] == "failed"
        assert "restarted" in job["error"]


def test_cloud_preview_consent_and_budget(client, monkeypatch):
    body = {"source": _upload(client), "mode": "vision", "llm_provider": "claude"}
    preview = client.post("/api/preview", json=body)
    assert preview.status_code == 200
    assert preview.json()["external"]
    assert client.post("/api/analyze", json=body).status_code == 422
    body.update(allow_cloud_llm=True, pixels_reviewed=True, budget_usd=1)
    monkeypatch.delenv("MEDCHECK_CLAUDE_ESTIMATED_COST_USD", raising=False)
    assert "estimate" in client.post("/api/analyze", json=body).json()["detail"]
    monkeypatch.setenv("MEDCHECK_CLAUDE_ESTIMATED_COST_USD", "2")
    assert "budget" in client.post("/api/analyze", json=body).json()["detail"]


def test_capabilities_and_storage_limit(client, settings):
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json()["max_upload_bytes"] == settings.max_upload_bytes
    assert {p["name"] for p in response.json()["providers"]} == {"local", "claude", "openai", "gemini"}
    settings.max_jobs = 1
    source = _upload(client)
    first = _submit(client, source)
    assert _finished(client, first)["status"] == "completed"
    blocked = client.post("/api/analyze", json={"source": source})
    assert blocked.status_code == 422
    assert "storage is full" in blocked.json()["detail"]
    assert client.delete(f"/api/jobs/{first}").status_code == 200
    assert _finished(client, _submit(client, source))["status"] == "completed"


def test_missing_and_unreadable_source_errors(client, settings):
    missing = str(Path(settings.data_root) / "missing.dcm")
    assert "does not exist" in client.post("/api/inspect", json={"source": missing}).json()["detail"]
    assert client.post("/api/inspect", json={"source": "upload:" + "f" * 32}).status_code == 422
    empty = Path(settings.data_root) / "empty"
    empty.mkdir()
    assert client.post("/api/inspect", json={"source": str(empty)}).status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/upload"),
        ("POST", "/api/analyze"),
        ("POST", "/api/jobs/missing/cancel"),
        ("DELETE", "/api/jobs/missing"),
        ("PATCH", "/api/jobs/missing/findings/0"),
        ("DELETE", "/api/uploads/missing"),
    ],
)
def test_cross_origin_mutations_rejected(client, method, path):
    assert client.request(method, path, headers={"Origin": "https://evil.example"}).status_code == 403


def test_corrupt_persisted_job_does_not_break_listing(settings):
    folder = Path(settings.state_dir) / ("b" * 32)
    folder.mkdir(parents=True)
    (folder / "status.json").write_text("not JSON")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/jobs").json() == []


@pytest.mark.parametrize("estimate", ["not-a-number", "NaN", "Infinity", "-1", "10001"])
def test_invalid_cost_estimate_blocks_budgeted_cloud_request(client, monkeypatch, estimate):
    monkeypatch.setenv("MEDCHECK_CLAUDE_ESTIMATED_COST_USD", estimate)
    body = {
        "source": _upload(client),
        "mode": "vision",
        "llm_provider": "claude",
        "allow_cloud_llm": True,
        "pixels_reviewed": True,
        "budget_usd": 5,
    }
    assert client.post("/api/preview", json=body).json()["estimated_cost_usd"] is None
    response = client.post("/api/analyze", json=body)
    assert response.status_code == 422
    assert "estimate" in response.json()["detail"]
    assert client.get("/api/jobs").json() == []


def test_no_usable_volume_fails_without_result(client, monkeypatch):
    def no_volume(self, context):
        context.volumes = {}
        return context

    monkeypatch.setattr("medcheck.web.jobs.PreprocessStep.run", no_volume)
    job = _finished(client, _submit(client, _upload(client)))
    assert job["status"] == "failed"
    assert "No usable image volumes" in job["error"]
    assert job["result"] is None
    assert client.patch(f"/api/jobs/{job['id']}/findings/0", json={"status": "confirmed"}).status_code == 422


def test_decoded_pixel_limit_checked_before_preprocessing(client, monkeypatch):
    from medcheck.core.context import DicomSeries

    def oversized(self, context):
        ds = pydicom.Dataset()
        ds.Rows = 16384
        ds.Columns = 16384
        context.dicom_series = [DicomSeries(slices=[ds])]
        return context

    def unexpected(self, context):
        pytest.fail("oversized study must stop before preprocessing")

    monkeypatch.setattr("medcheck.web.jobs.IngestStep.run", oversized)
    monkeypatch.setattr("medcheck.web.jobs.PreprocessStep.run", unexpected)
    job = _finished(client, _submit(client, _upload(client)))
    assert job["status"] == "failed"
    assert "decoded image limit" in job["error"]
