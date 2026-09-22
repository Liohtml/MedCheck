"""Authenticated local workbench API, with bounded uploads and background jobs."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image

from medcheck.core.config import Settings
from medcheck.pipeline.exports import dicom_sr, fhir_report
from medcheck.pipeline.report import generate_html_report, generate_pdf_report
from medcheck.web.jobs import AnalyzeRequest, JobStore, ReviewRequest, SourceRequest, context_from_report, preview


def install_api(app: FastAPI, settings: Settings, guard: Any, rate_limit: Any) -> None:  # noqa: C901 - route factory
    router = APIRouter(prefix="/api", dependencies=[Depends(guard)])

    def store(request: Request) -> JobStore:
        # Initialized by app lifespan in real deployments; tests may skip lifespan.
        with app.state.store_lock:
            if getattr(app.state, "jobs", None) is None:
                app.state.jobs = JobStore(settings)
            result: JobStore = app.state.jobs
            return result

    @router.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        from medcheck.llm.claude import ClaudeProvider
        from medcheck.llm.gemini import GeminiProvider
        from medcheck.llm.local import LocalLLMProvider
        from medcheck.llm.openai_provider import OpenAIProvider

        providers = [ClaudeProvider(), OpenAIProvider(), GeminiProvider(), LocalLLMProvider()]
        return {
            "ocr_available": importlib.util.find_spec("pytesseract") is not None
            and shutil.which("tesseract") is not None,
            "providers": [
                {"name": p.name, "model": getattr(p, "model", ""), "available": p.check_available()} for p in providers
            ],
            "max_vision_images": settings.max_vision_images,
            "max_upload_bytes": settings.max_upload_bytes,
            "supported_formats": ["json", "html", "pdf", "fhir", "dicom-sr"],
            "pricing": {"source": "operator-configured estimates", "billing_guarantee": False},
        }

    @router.post("/upload", dependencies=[Depends(rate_limit)])
    async def upload(file: UploadFile, request: Request) -> dict[str, str]:
        db = store(request)
        name = Path(file.filename or "scan.zip").name
        suffix = Path(name).suffix.lower()
        if suffix not in {".zip", ".dcm", ".dicom"}:
            raise HTTPException(422, "Upload a DICOM ZIP archive or a .dcm file.")
        if len(list(db.uploads.iterdir())) >= settings.max_jobs:
            raise HTTPException(409, "Upload storage is full. Delete previous uploads before adding another.")
        token = uuid4().hex
        # Single DICOM files live in their own directory, preventing mixed uploads.
        destination = db.uploads / f"{token}{suffix}"
        total = 0
        try:
            with destination.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise HTTPException(413, "Upload exceeds the configured size limit.")
                    output.write(chunk)
            if total == 0:
                raise HTTPException(422, "The uploaded file is empty.")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {"source": f"upload:{token}", "filename": name}

    @router.delete("/uploads/{token}")
    def delete_upload(token: str, request: Request) -> dict[str, str]:
        db = store(request)
        try:
            path = db.resolve_source(f"upload:{token}")
            # Jobs read source files only during ingest; refuse cleanup while anything is active.
            if any(j["status"] in {"queued", "running"} for j in db.jobs.values()):
                raise ValueError("Wait for active analyses to stop before deleting uploads.")
            path.unlink()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "deleted"}

    @router.post("/inspect", dependencies=[Depends(rate_limit)])
    def inspect_source(req: SourceRequest, request: Request) -> dict[str, Any]:
        try:
            return store(request).inspect(req.source)
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/preview")
    def preview_analysis(req: AnalyzeRequest) -> dict[str, Any]:
        return preview(req, settings)

    @router.post("/analyze", status_code=202, dependencies=[Depends(rate_limit)])
    def analyze(req: AnalyzeRequest, request: Request) -> dict[str, Any]:
        try:
            return store(request).submit(req)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/jobs")
    def list_jobs(request: Request) -> list[dict[str, Any]]:
        db = store(request)
        with db.lock:
            return [{k: v for k, v in job.items() if k != "result"} for job in db.jobs.values()]

    @router.get("/jobs/{job_id}")
    def job(job_id: str, request: Request) -> dict[str, Any]:
        try:
            return store(request).get(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Analysis not found.") from exc

    @router.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request) -> dict[str, Any]:
        job(job_id, request)
        return store(request).cancel(job_id)

    @router.delete("/jobs/{job_id}")
    def delete(job_id: str, request: Request) -> dict[str, str]:
        try:
            store(request).delete(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Analysis not found.") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(409, "Analysis files could not be deleted. Check storage access and retry.") from exc
        return {"status": "deleted"}

    @router.patch("/jobs/{job_id}/findings/{index}")
    def review(job_id: str, index: int, req: ReviewRequest, request: Request) -> dict[str, Any]:
        job(job_id, request)
        try:
            return store(request).review(job_id, index, req)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/jobs/{job_id}/images/{series_index}/{slice_index}")
    def image(job_id: str, series_index: int, slice_index: int, request: Request) -> Response:
        try:
            arr = store(request).read_slice(job_id, series_index, slice_index)
        except KeyError as exc:
            raise HTTPException(404, "Analysis not found.") from exc
        except IndexError as exc:
            raise HTTPException(404, "Image not found.") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        png = io.BytesIO()
        Image.fromarray((arr.clip(0, 1) * 255).astype("uint8")).save(png, format="PNG")
        return Response(png.getvalue(), media_type="image/png")

    @router.get("/jobs/{job_id}/report")
    def download(job_id: str, request: Request, format: str = "json") -> Response:
        current = job(job_id, request)
        if current["status"] != "completed":
            raise HTTPException(409, "Wait for the analysis to finish before downloading.")
        db = store(request)
        report = current["result"]
        ctx = context_from_report(report, db.root / job_id)
        headers = {"Content-Disposition": f'attachment; filename="medcheck-{job_id}.{format}"'}
        if format == "json":
            return Response(json.dumps(report, indent=2), media_type="application/json", headers=headers)
        if format == "fhir":
            headers["Content-Disposition"] = f'attachment; filename="medcheck-{job_id}-fhir.json"'
            return Response(
                json.dumps(fhir_report(report), indent=2), media_type="application/fhir+json", headers=headers
            )
        if format == "dicom-sr":
            headers["Content-Disposition"] = f'attachment; filename="medcheck-{job_id}-sr.dcm"'
            return Response(dicom_sr(ctx, report), media_type="application/dicom", headers=headers)
        if format in {"pdf", "html"}:
            path = generate_pdf_report(ctx) if format == "pdf" else generate_html_report(ctx)
            return FileResponse(path, filename=f"medcheck-{job_id}.{format}")
        raise HTTPException(422, "Unsupported report format.")

    app.include_router(router)
