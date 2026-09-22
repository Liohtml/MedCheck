"""Bounded single-process jobs and study storage for the local research workbench."""

from __future__ import annotations

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, Field, model_validator

from medcheck import __version__
from medcheck.core.config import Settings
from medcheck.core.context import ClinicalContext, PatientInfo, PipelineContext, StructureFinding, StudyInfo
from medcheck.pipeline.ingest import IngestStep
from medcheck.pipeline.ml_analysis import MLAnalysisStep
from medcheck.pipeline.preprocess import PreprocessStep
from medcheck.pipeline.privacy import DeidentifyStep, apply_pixel_redactions
from medcheck.pipeline.reconcile import ReconcileStep
from medcheck.pipeline.report import generate_json_report
from medcheck.pipeline.vision_analysis import VisionAnalysisStep
from medcheck.providers.local import LocalProvider


class AnalyzeRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2048)
    provider: Literal["local"] | None = None
    study_uid: str = Field(default="", max_length=128)
    mode: Literal["local", "vision"] = "local"
    llm_provider: Literal["local", "claude", "openai", "gemini"] = "local"
    anatomy: str = Field(default="", max_length=80)
    symptoms: str = Field(default="", max_length=10000)
    trauma: str = Field(default="", max_length=10000)
    suspected_diagnosis: str = Field(default="", max_length=10000)
    report_format: Literal["json", "html", "pdf", "fhir", "dicom-sr"] = "json"
    language: Literal["en", "de", "fr", "es"] = "en"
    allow_cloud_llm: bool = False
    deidentify: bool = True
    pixels_reviewed: bool = False
    ocr_redact: bool = False
    budget_usd: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    official_report: str = Field(default="", max_length=100000)
    redactions: dict[str, list[list[int]]] = Field(default_factory=dict)


class SourceRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2048)


class ReviewRequest(BaseModel):
    status: Literal["confirmed", "rejected", "edited"]
    findings: str | None = Field(default=None, max_length=20000)
    note: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def require_edit(self) -> ReviewRequest:
        if self.status == "edited" and not (self.findings or "").strip():
            raise ValueError("An edited finding requires replacement text.")
        return self


def study_warnings(slices: list[Any]) -> list[str]:
    """Cheap metadata preflight before any decoding or model invocation."""
    warnings = []
    if any(not hasattr(ds, "ImagePositionPatient") or not hasattr(ds, "ImageOrientationPatient") for ds in slices):
        warnings.append("Some images have no complete position/orientation metadata; slice order needs review.")
    if any(int(getattr(ds, "NumberOfFrames", 1)) != 1 or int(getattr(ds, "SamplesPerPixel", 1)) != 1 for ds in slices):
        warnings.append("Multiframe or color images are not supported and will be excluded.")
    shapes = {(getattr(ds, "Rows", 0), getattr(ds, "Columns", 0)) for ds in slices}
    if len(shapes) > 1:
        warnings.append("Mixed image dimensions detected; images outside the dominant shape will be excluded.")
    positions = [tuple(ds.ImagePositionPatient) for ds in slices if hasattr(ds, "ImagePositionPatient")]
    if len(set(positions)) != len(positions):
        warnings.append("Repeated image positions detected; review for duplicate acquisitions.")
    if any(str(getattr(ds, "BurnedInAnnotation", "")) != "NO" for ds in slices):
        warnings.append("Embedded patient text has not been ruled out. Review pixels before sharing images.")
    return warnings


def preview(req: AnalyzeRequest, settings: Settings) -> dict[str, Any]:
    external = req.mode == "vision" and req.llm_provider != "local"
    # Operator-supplied conservative per-analysis estimate, never a fabricated price.
    raw = os.environ.get(f"MEDCHECK_{req.llm_provider.upper()}_ESTIMATED_COST_USD", "")
    estimate = None
    if external and raw:
        try:
            number = float(raw)
            if 0 <= number < 10000:
                estimate = number
        except ValueError:
            pass
    if not external:
        estimate = 0.0
    return {
        "provider": req.llm_provider if req.mode == "vision" else "statistical",
        "external": external,
        "image_limit": settings.max_vision_images if req.mode == "vision" else 0,
        "estimated_cost_usd": estimate,
        "context_fields": [key for key in ("symptoms", "trauma", "suspected_diagnosis") if getattr(req, key)],
        "warnings": ["Cost is an operator estimate, not a billing guarantee; retries may incur additional charges."]
        if external
        else [],
    }


def context_from_report(report: dict[str, Any], folder: Path) -> PipelineContext:
    ctx = PipelineContext(output_dir=str(folder), report_language=report.get("language", "en"))
    ctx.study_instance_uid = report.get("study_instance_uid", "")
    ctx.deidentify = report.get("deidentified", False)
    ctx.pixels_reviewed = report.get("privacy", {}).get("pixels_reviewed", False)
    ctx.patient = PatientInfo(**report["patient"])
    ctx.study = StudyInfo(**report["study"])
    allowed = {f.name for f in fields(StructureFinding)}
    ctx.findings = [StructureFinding(**{k: v for k, v in f.items() if k in allowed}) for f in report["findings"]]
    for name in (
        "overall_impression",
        "clinical_correlation",
        "limitations",
        "review_history",
        "analysis_provenance",
        "quality_checks",
        "reconciliation",
    ):
        setattr(ctx, name, report.get(name, getattr(ctx, name)))
    return ctx


def _close_volumes(context: PipelineContext) -> None:
    """Release owned mmap handles explicitly, including when NumPy views survive.

    Store callers hold the lock; read_slice only exposes independent copies so
    a viewer request cannot use a mapping while it is being closed.
    """
    for volume in context.volumes.values():
        mapping = getattr(volume, "_mmap", None)
        if mapping is not None:
            mapping.close()
    context.volumes.clear()


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path(settings.state_dir).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir(mode=0o700, exist_ok=True)
        self.data_root = Path(settings.data_root).resolve()
        self.lock = threading.RLock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.contexts: dict[str, PipelineContext] = {}
        self.cancels: dict[str, threading.Event] = {}
        self.pool = ThreadPoolExecutor(max_workers=max(1, settings.job_workers), thread_name_prefix="medcheck")
        # Interrupted jobs are recorded explicitly on restart; raw images aren't persisted twice.
        for path in self.root.glob("*/status.json"):
            try:
                job = json.loads(path.read_text())
                if job["status"] in {"queued", "running"}:
                    job.update(
                        status="failed", error="Server restarted before analysis finished. Start a new analysis."
                    )
                job["viewer_available"] = False
                if job["id"] != path.parent.name:
                    continue
                self.jobs[job["id"]] = job
                if job["status"] == "completed" and (path.parent / "volumes.json").exists():
                    ctx = context_from_report(job["result"], path.parent)
                    keys = json.loads((path.parent / "volumes.json").read_text())
                    ctx.volumes = {
                        key: np.load(path.parent / f"volume-{index}.npy", mmap_mode="r", allow_pickle=False)
                        for index, key in enumerate(keys)
                    }
                    self.contexts[job["id"]] = ctx
                    job["viewer_available"] = True
            except (OSError, ValueError, KeyError):
                continue

    def resolve_source(self, source: str) -> Path:
        if source.startswith("upload:"):
            token = source.removeprefix("upload:")
            if len(token) != 32 or any(c not in "0123456789abcdef" for c in token):
                raise ValueError("Invalid upload identifier")
            matches = list(self.uploads.glob(f"{token}.*"))
            if len(matches) != 1:
                raise ValueError("Upload not found. Upload the file again.")
            return matches[0]
        path = Path(source).expanduser().resolve()
        if not path.is_relative_to(self.data_root):
            raise ValueError("Choose an uploaded file or a path inside MEDCHECK_DATA_ROOT.")
        if not path.exists():
            raise ValueError("Source does not exist. Upload a DICOM ZIP or check the server data folder.")
        # Disallow symlinks below approved root too (LocalProvider recursively reads files).
        if path.is_dir() and any(p.is_symlink() for p in path.rglob("*")):
            raise ValueError("Symbolic links are not accepted in server data directories.")
        return path

    def inspect(self, source: str) -> dict[str, Any]:
        series = LocalProvider().fetch(str(self.resolve_source(source)), {})
        studies: dict[str, dict[str, Any]] = {}
        for item in series:
            uid = str(item.metadata.get("study_instance_uid", ""))
            ds = item.slices[0]
            study = studies.setdefault(
                uid,
                {
                    "study_uid": uid,
                    "description": str(getattr(ds, "StudyDescription", "Study")),
                    "date": str(getattr(ds, "StudyDate", "")),
                    "series": [],
                    "warnings": [],
                },
            )
            study["series"].append(
                {
                    "name": item.description,
                    "series_uid": item.metadata.get("series_instance_uid", ""),
                    "slices": len(item.slices),
                    "modality": item.modality,
                }
            )
            study["warnings"] = list(dict.fromkeys([*study["warnings"], *study_warnings(item.slices)]))
        if not studies:
            raise ValueError("No readable DICOM images found in this source.")
        return {"source": source, "studies": list(studies.values())}

    def _save(self, job_id: str) -> None:
        folder = self.root / job_id
        folder.mkdir(mode=0o700, exist_ok=True)
        temp = folder / "status.tmp"
        temp.write_text(json.dumps(self.jobs[job_id]), encoding="utf-8")
        temp.replace(folder / "status.json")

    def submit(self, req: AnalyzeRequest) -> dict[str, Any]:
        if req.mode == "vision" and req.llm_provider != "local":
            if not req.allow_cloud_llm or not req.pixels_reviewed:
                raise ValueError("Cloud analysis requires consent and review of images for identifying information.")
        source = self.resolve_source(req.source)
        plan = preview(req, self.settings)
        estimate = plan["estimated_cost_usd"]
        if req.budget_usd is not None and (estimate is None or estimate > req.budget_usd):
            raise ValueError(
                "Cost estimate is unavailable or exceeds your budget. Configure an estimate or adjust the budget."
            )
        with self.lock:
            if len(self.jobs) >= self.settings.max_jobs:
                raise ValueError("Job storage is full. Delete completed analyses before starting another.")
            job_id = uuid4().hex
            self.jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "step": "queued",
                "progress": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "result": None,
                "viewer_available": False,
                "cancel_requested": False,
            }
            self.cancels[job_id] = threading.Event()
            self._save(job_id)
            self.pool.submit(self._run, job_id, req, str(source), plan)
            return dict(self.jobs[job_id])

    def _run(self, job_id: str, req: AnalyzeRequest, source: str, plan: dict[str, Any]) -> None:  # noqa: C901
        ctx = PipelineContext(
            source=source,
            provider_name="local",
            study_instance_uid=req.study_uid,
            clinical_context=ClinicalContext(
                symptoms=req.symptoms,
                trauma=req.trauma,
                suspected_diagnosis=req.suspected_diagnosis,
                anatomy=req.anatomy,
            ),
            report_format=req.report_format,
            report_language=req.language,
            llm_provider=req.llm_provider,
            deidentify=req.deidentify,
            allow_external_llm=req.allow_cloud_llm,
            pixels_reviewed=req.pixels_reviewed,
            official_report=req.official_report,
            redactions=req.redactions,
            output_dir=str(self.root / job_id),
        )
        ctx.analysis_provenance.update(
            {
                "app_version": __version__,
                "run_id": job_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "transmission_preview": plan,
                "settings": {
                    "mode": req.mode,
                    "deidentify": req.deidentify,
                    "image_limit": self.settings.max_vision_images,
                },
            }
        )
        steps = [IngestStep(), DeidentifyStep(), PreprocessStep(), MLAnalysisStep()]
        if req.mode == "vision":
            steps.append(VisionAnalysisStep())
        steps.append(ReconcileStep())
        try:
            for index, step in enumerate(steps):
                if self.cancels[job_id].is_set():
                    break
                with self.lock:
                    self.jobs[job_id].update(status="running", step=step.name, progress=int(index / len(steps) * 95))
                    self._save(job_id)
                # Web default must never trigger model weight downloads.
                ctx.step_config = {"backend": "statistical"} if step.name == "ml_analysis" else {}
                ctx = step.run(ctx)
                if step.name == "ingest":
                    pixels = sum(
                        int(getattr(ds, "Rows", 0))
                        * int(getattr(ds, "Columns", 0))
                        * int(getattr(ds, "NumberOfFrames", 1))
                        for s in ctx.dicom_series
                        for ds in s.slices
                    )
                    if pixels > 128 * 1024 * 1024:
                        raise ValueError("Study exceeds the decoded image limit. Select a smaller study.")
                if step.name == "preprocess":
                    if not ctx.volumes:
                        raise ValueError("No usable image volumes. Check the DICOM encoding and quality warnings.")
                    ctx.step_config["ocr"] = req.ocr_redact
                    apply_pixel_redactions(ctx)
            with self.lock:
                if self.cancels[job_id].is_set():
                    self.jobs[job_id].update(status="cancelled", step="cancelled")
                else:
                    if req.mode == "local":
                        ctx.overall_impression = (
                            "Local image quality and relative image statistics completed. "
                            "No diagnostic findings were generated."
                        )
                    ctx.analysis_provenance["completed_at"] = datetime.now(timezone.utc).isoformat()
                    folder = self.root / job_id
                    for index, (key, volume) in enumerate(ctx.volumes.items()):
                        path = folder / f"volume-{index}.npy"
                        np.save(path, volume, allow_pickle=False)
                        ctx.volumes[key] = np.load(path, mmap_mode="r", allow_pickle=False)
                    (folder / "volumes.json").write_text(json.dumps(list(ctx.volumes)), encoding="utf-8")
                    ctx.dicom_series.clear()
                    self.contexts[job_id] = ctx
                    self.jobs[job_id].update(
                        status="completed",
                        step="completed",
                        progress=100,
                        result=json.loads(generate_json_report(ctx)),
                        viewer_available=True,
                    )
                self._save(job_id)
        except Exception as exc:
            # Known input failures are actionable; provider responses can contain PHI/secrets.
            message = (
                str(exc)
                if isinstance(exc, (ValueError, PermissionError))
                else f"{type(exc).__name__}: analysis failed. Check local configuration and retry."
            )
            with self.lock:
                cancelled = self.cancels[job_id].is_set()
                self.jobs[job_id].update(
                    status="cancelled" if cancelled else "failed", error=None if cancelled else message
                )
                self._save(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError("Analysis not found")
            return cast(
                dict[str, Any], json.loads(json.dumps(self.jobs[job_id]))
            )  # detach response from worker mutation

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = self.get(job_id)
            if job["status"] in {"queued", "running"}:
                self.cancels[job_id].set()
                self.jobs[job_id]["cancel_requested"] = True
                self._save(job_id)
            return self.get(job_id)

    def read_slice(self, job_id: str, series_index: int, slice_index: int) -> np.ndarray[Any, np.dtype[Any]]:
        """Copy one image under the deletion lock; no file-backed views escape."""
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError("Analysis not found")
            context = self.contexts.get(job_id)
            if context is None:
                raise ValueError("Image viewer unavailable. Run the analysis again.")
            volumes = list(context.volumes.values())
            if not 0 <= series_index < len(volumes) or not 0 <= slice_index < volumes[series_index].shape[0]:
                raise IndexError("Image not found")
            return np.array(volumes[series_index][slice_index], copy=True)

    def delete(self, job_id: str) -> None:
        with self.lock:
            job = self.get(job_id)
            if job["status"] in {"queued", "running"}:
                raise ValueError("Cancel the analysis and wait for it to stop before deleting it.")
            context = self.contexts.pop(job_id, None)
            if context:
                _close_volumes(context)
            self.jobs[job_id]["viewer_available"] = False
            try:
                shutil.rmtree(self.root / job_id)
            except OSError:
                # A partial deletion must not disappear from the catalog or be
                # reported as successful. Restore status for a later retry.
                self._save(job_id)
                raise ValueError("Analysis files could not be deleted. Close other file users and retry.") from None
            self.jobs.pop(job_id)
            self.cancels.pop(job_id, None)

    def review(self, job_id: str, index: int, req: ReviewRequest) -> dict[str, Any]:
        with self.lock:
            job = self.get(job_id)
            if job["status"] != "completed":
                raise ValueError("Only completed analyses can be reviewed.")
            report = job["result"]
            if not 0 <= index < len(report["findings"]):
                raise ValueError("Finding does not exist.")
            finding = report["findings"][index]
            before = dict(finding)
            finding["review_status"] = req.status
            if req.status == "edited":
                finding["findings"] = req.findings
            event = {
                "finding_index": index,
                "at": datetime.now(timezone.utc).isoformat(),
                "before": before,
                "after": dict(finding),
                "note": req.note,
            }
            report["review_history"].append(event)
            self.jobs[job_id]["result"] = report
            if job_id in self.contexts:
                ctx = self.contexts[job_id]
                ctx.findings[index].review_status = req.status
                ctx.findings[index].findings = finding["findings"]
                ctx.review_history = report["review_history"]
            self._save(job_id)
            return cast(dict[str, Any], report)

    def close(self) -> None:
        with self.lock:
            for event in self.cancels.values():
                event.set()
            self.pool.shutdown(wait=False, cancel_futures=True)
            for context in self.contexts.values():
                _close_volumes(context)
            self.contexts.clear()
