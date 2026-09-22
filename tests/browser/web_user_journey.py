"""Browser smoke test using synthetic images only.

Run a local server, then:
  uv run --with playwright python tests/browser/web_user_journey.py
Set PLAYWRIGHT_CHROMIUM_EXECUTABLE if Chromium is installed outside Playwright's default.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid


def synthetic_zip(directory: Path) -> Path:
    study_uid = generate_uid()
    archive = directory / "synthetic-study.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for series in range(2):
            series_uid = generate_uid()
            for index in range(3):
                meta = FileMetaDataset()
                meta.TransferSyntaxUID = ExplicitVRLittleEndian
                meta.MediaStorageSOPClassUID = MRImageStorage
                meta.MediaStorageSOPInstanceUID = generate_uid()
                path = directory / f"series-{series}-slice-{index}.dcm"
                ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
                ds.SOPClassUID = meta.MediaStorageSOPClassUID
                ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
                ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series_uid
                ds.PatientName = "SYNTHETIC^TEST"
                ds.PatientID = "BROWSER-QA"
                ds.StudyDescription = "Synthetic browser QA"
                ds.SeriesDescription = f"Knee T2 axial {series + 1}"
                ds.Modality = "MR"
                ds.InstanceNumber = index + 1
                ds.ImagePositionPatient = [0, 0, index * 2]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.PixelSpacing = [1, 1]
                ds.SliceThickness = 2
                ds.Rows, ds.Columns = 32, 32
                ds.SamplesPerPixel = 1
                ds.PhotometricInterpretation = "MONOCHROME2"
                ds.BitsAllocated = ds.BitsStored = 16
                ds.HighBit, ds.PixelRepresentation = 15, 0
                ds.PixelData = (np.arange(1024, dtype=np.uint16).reshape(32, 32) + index * 20).tobytes()
                ds.save_as(path, enforce_file_format=True)
                output.write(path, path.name)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--screenshots", default="artifacts/ui")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()
    screenshots = Path(args.screenshots)
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, sync_playwright() as p:
        archive = synthetic_zip(Path(temporary))
        browser = p.chromium.launch(
            headless=True,
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"),
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda msg: (
                errors.append(msg.text) if msg.type == "error" and "Content Security Policy" in msg.text else None
            ),
        )
        page.goto(args.url + "/?lang=de")
        page.wait_for_load_state("networkidle")
        page.locator('#pane-1 [data-goto="2"]').click()
        expect(page.locator("#formAlert")).to_contain_text("Wähle zuerst")
        expect(page.locator("#pane-1")).to_be_visible()
        page.locator("#fileInput").set_input_files(
            {"name": "unsupported.png", "mimeType": "image/png", "buffer": b"invalid"}
        )
        expect(page.locator("#formAlert")).to_contain_text(".dcm")
        if args.api_key:
            page.locator(".connection-settings summary").click()
            page.locator("#apiKey").fill("deliberately-wrong-key")
            page.locator("#fileInput").set_input_files(archive)
            expect(page.locator("#formAlert")).to_contain_text("API key")
            page.locator("#apiKey").fill(args.api_key)
            page.locator("#apiKey").blur()
        page.locator("#fileInput").set_input_files(
            {"name": "broken.dcm", "mimeType": "application/dicom", "buffer": b"not a DICOM dataset"}
        )
        expect(page.locator("#uploadStatus")).to_contain_text("Upload fehlgeschlagen")
        expect(page.locator("#formAlert")).to_be_focused()
        page.locator("#fileInput").set_input_files(archive)
        expect(page.locator("#studyBlock")).to_be_visible(timeout=30000)
        expect(page.locator("#studySummary")).to_contain_text("6 Bilder")
        expect(page.locator("#studySummary .alert-warning")).to_contain_text("Embedded patient text")
        page.screenshot(path=str(screenshots / "desktop-import.png"), full_page=True)
        page.locator('#pane-1 [data-goto="2"]').click()
        expect(page.locator("#symptoms")).to_be_visible()
        page.locator("#symptoms").fill("Synthetic QA only")
        page.locator("#anatomy").select_option("knee")
        page.locator('#pane-2 [data-goto="3"]').click()
        expect(page.locator("#modelSelect")).to_have_value("local")
        expect(page.locator("#consentBlock")).not_to_be_visible()
        page.locator("#startBtn").click()
        expect(page.locator("#progressLabel")).to_have_text("Analyse abgeschlossen", timeout=60000)
        expect(page.locator("#progressBar")).to_have_attribute("aria-valuenow", "100")
        expect(page.locator("#resultsContent")).to_contain_text("Qualitätsprüfung erstellt keine")
        expect(
            page.locator("#resultsContent summary").filter(has_text="Abgleich mit vorhandenem Befund")
        ).to_have_count(0)
        assert (
            page.locator("#progressFill").bounding_box()["width"]
            == page.locator("#progressBar").bounding_box()["width"]
        )
        expect(page.locator("#downloads")).to_be_visible()
        expect(page.locator("#viewer")).to_be_visible()
        expect(page.locator("#sliceImage")).to_have_attribute("width", "32")
        page.locator("#sliceRange").fill("2")
        expect(page.locator("#sliceLabel")).to_have_text("Schicht 3 / 3")
        page.locator("#seriesSelect").select_option("1")
        expect(page.locator("#sliceLabel")).to_have_text("Schicht 1 / 3")
        page.reload()
        page.wait_for_load_state("networkidle")
        if args.api_key:
            expect(page.locator("#resumeBtn")).to_be_visible()
            page.locator(".connection-settings summary").click()
            page.locator("#apiKey").fill(args.api_key)
            page.locator("#resumeBtn").click()
        expect(page.locator("#studyBlock")).to_be_visible()
        expect(page.locator("#progressLabel")).to_have_text("Analyse abgeschlossen")
        expect(page.locator("#viewer")).to_be_visible()
        page.locator('[data-step="3"]').click()
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Herunterladen JSON", exact=True).click()
        report = json.loads(Path(downloaded.value.path()).read_text())
        assert "limitations" in report
        page.screenshot(path=str(screenshots / "desktop-results.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        page.screenshot(path=str(screenshots / "mobile-results.png"), full_page=True)
        # Deterministic UI-only edge cases: cancellation and human review.
        # The happy path above uses the real backend; these routes avoid timing races/cloud calls.
        state = {"cancelled": False, "review": None, "analyze": None}

        def start_edge(route):
            state["analyze"] = route.request.post_data_json
            route.fulfill(json={"id": "ui-edge", "status": "queued"})

        page.route("**/api/analyze", start_edge)
        page.route(
            "**/api/capabilities",
            lambda route: route.fulfill(
                json={
                    "ocr_available": True,
                    "providers": [{"name": "claude", "available": True, "model": "UI fixture"}],
                }
            ),
        )
        # Trigger a capability refresh, then exercise OCR request wiring without a cloud invocation.
        if not page.locator("#apiKey").is_visible():
            page.locator('[data-step="1"]').click()
            page.locator(".connection-settings summary").click()
        page.locator("#apiKey").dispatch_event("change")
        expect(page.locator("#ocrBlock")).not_to_have_attribute("hidden", "")
        page.locator('[data-step="3"]').click()
        page.locator("#modelSelect").select_option("claude")
        page.locator("#consentCheck").check()
        page.locator("#pixelsReviewed").check()
        page.locator("#ocrRedact").check()

        def edge_status(route):
            route.fulfill(
                json={
                    "id": "ui-edge",
                    "status": "cancelled" if state["cancelled"] else "running",
                    "progress": 20,
                    "step": "Synthetic slow step",
                }
            )

        def cancel(route):
            state["cancelled"] = True
            route.fulfill(json={"status": "cancelled"})

        page.route("**/api/jobs/ui-edge", edge_status)
        page.route("**/api/jobs/ui-edge/cancel", cancel)
        page.locator("#startBtn").click()
        expect(page.locator("#cancelBtn")).to_be_visible()
        page.locator("#cancelBtn").click()
        assert state["analyze"]["ocr_redact"] is True
        expect(page.locator("#progressLabel")).to_contain_text("abgebrochen", timeout=5000)
        expect(page.locator("#startBtn")).to_be_enabled()
        page.locator("#modelSelect").select_option("local")
        page.unroute("**/api/jobs/ui-edge", edge_status)
        synthetic_result = {
            "findings": [
                {
                    "name": "Synthetic finding",
                    "findings": "Review fixture",
                    "status": "uncertain",
                    "image_references": [{"series_name": "Synthetic series", "slice_index": 1}],
                }
            ],
            "limitations": ["Synthetic UI fixture only"],
            "series": [{"key": "Synthetic series", "slices": 3}],
        }
        disconnected = [True]

        def reconnect_status(route):
            if disconnected[0]:
                disconnected[0] = False
                route.abort("failed")
                return
            route.fulfill(
                json={
                    "id": "ui-edge",
                    "status": "completed",
                    "progress": 100,
                    "result": synthetic_result,
                }
            )

        page.route("**/api/jobs/ui-edge", reconnect_status)

        def review(route):
            state["review"] = route.request.post_data_json
            synthetic_result["findings"][0]["review_status"] = state["review"]["status"]
            synthetic_result["findings"][0]["findings"] = state["review"]["findings"]
            route.fulfill(json=synthetic_result)

        page.route("**/api/jobs/ui-edge/findings/0", review)
        preview_image = io.BytesIO()
        Image.new("L", (32, 32), color=128).save(preview_image, format="PNG")
        page.route(
            "**/api/jobs/ui-edge/images/*/*",
            lambda route: route.fulfill(body=preview_image.getvalue(), content_type="image/png"),
        )
        page.locator("#startBtn").click()
        expect(page.locator("#resumeBtn")).to_be_visible()
        page.locator("#resumeBtn").click()
        expect(page.locator("#finding-0")).to_be_visible()
        page.get_by_role("button", name="Referenziertes Bild öffnen").click()
        expect(page.locator("#sliceLabel")).to_have_text("Schicht 2 / 3")
        page.locator("#finding-0").select_option("edited")
        page.locator("#finding-0-text").fill("Corrected synthetic finding")
        page.locator("#finding-0-note").fill("Verified in browser test")
        page.get_by_role("button", name="Prüfung speichern").click()
        expect(page.get_by_text("Prüfung gespeichert", exact=True)).to_be_visible()
        assert state["review"] == {
            "status": "edited",
            "findings": "Corrected synthetic finding",
            "note": "Verified in browser test",
        }
        # Render the persisted review again, then edit without changing its status first.
        page.locator("#startBtn").click()
        expect(page.locator("#finding-0")).to_have_value("edited")
        expect(page.locator("#finding-0-text")).to_be_enabled()
        expect(page.locator("#finding-0-text")).to_have_value("Corrected synthetic finding")
        expect(page.get_by_role("button", name="Prüfung speichern")).to_be_disabled()
        page.locator("#finding-0-text").fill("Second correction after render")
        expect(page.get_by_role("button", name="Prüfung speichern")).to_be_enabled()
        page.get_by_role("button", name="Prüfung speichern").click()
        expect(page.get_by_text("Prüfung gespeichert", exact=True)).to_be_visible()
        assert state["review"]["findings"] == "Second correction after render"
        page.locator("#deleteBtn").click()
        expect(page.locator("#resultsContent")).to_have_text("Analyse und hochgeladene Datei gelöscht.")
        expect(page.locator("#pane-1")).to_be_visible()
        expect(page.locator("#studyBlock")).not_to_be_visible()
        page.unroute_all()
        # Fresh mobile navigation: real keyboard focus and validation.
        page.goto(args.url + "/?lang=de")
        page.wait_for_load_state("networkidle")
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Zum Inhalt springen")).to_be_focused()
        page.screenshot(path=str(screenshots / "mobile-upload.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print("PASS: real ZIP import, local job, viewer, JSON download, mobile, keyboard, no JS errors")


if __name__ == "__main__":
    main()
