# Local research workbench

Run `uv sync --extra dev`, then `uv run medcheck serve`. Open
http://127.0.0.1:8080. Upload a DICOM ZIP or a single `.dcm`/`.dicom` file,
select the study, check metadata warnings, and start a local analysis. Local
browser analysis uses statistics and never downloads model weights. It does
not generate diagnostic findings. DICOMDIR is supported through the CLI or
an archive containing the directory and referenced files.

The result includes quality warnings, a grayscale slice viewer, relative
image-difference scores, JSON/HTML/PDF downloads, and analysis provenance.
Vision results can reference only images actually submitted to the model.
Clicking a valid reference selects that image; an absent reference does not
imply that localization has been established. Windowing, diagnostic display
calibration, 3-D reconstruction and clinical viewing are outside this viewer's
scope.

## Vision and privacy

Install a provider extra or `uv sync --extra cloud`. A locally installed
vision model server is configured separately; see [models](models.md).
Before cloud analysis the UI displays provider, image limit, populated clinical
context fields and any configured cost estimate. Consent and explicit review
of pixels for embedded identifiers/recognizable anatomy are both required.
Review the images externally or perform a local analysis first. This is an
operator attestation; MedCheck cannot certify that the review was adequate.

Metadata de-identification is on by default in the browser. It creates copies,
replaces identifiers and UIDs, removes unapproved/private fields recursively,
replaces free-text series labels, and removes known identifiers from contextual
text. Original uploaded files remain unchanged. Unknown identifying text may
remain in free-text inputs. Optional local Tesseract OCR masks detected text,
but can miss it; optional explicit rectangular masks apply to normalized
volumes. Neither mechanism is certified anonymization or automatic facial
defacing. See the privacy flags in JSON and the [model card](model-card.md).

OCR appears in the UI only when the `privacy` extra and Tesseract are present.
CLI: `medcheck analyze scans --deidentify --ocr-redact`. For the API, use
`ocr_redact: true`, or `redactions: {"Series 1": [[x, y, width, height]]}`;
mask coordinates refer to preprocessed images, and de-identified series use
`Series 1`, `Series 2`, etc. An OCR failure stops analysis rather than silently
sending unmasked data.

Cloud cost estimates come from `MEDCHECK_<PROVIDER>_ESTIMATED_COST_USD` and
must be set by the operator using current provider rates and conservative
image/token/retry assumptions. A requested budget rejects an unknown or larger
estimate. This is an estimated-spend gate, not a hard billing cap; provider-side
account limits should enforce actual spending. MedCheck makes no model quality
claims and never silently switches to a different cloud vendor.

## Jobs and retained data

The service is a single-process, single-user workbench. Run one uvicorn worker.
An API key is shared access control, not tenant isolation or user identity.
All `/api` routes, including downloads and images, require that key when set.
Browser API keys stay in memory. Session storage contains only opaque job/upload
IDs and a selected study ID; refresh prompts for the key again if configured.

`MEDCHECK_STATE_DIR` (default `.medcheck`) contains original uploads,
normalized viewer volumes, results and review history. Completed viewer volumes
are loaded through memory maps rather than retaining original datasets in RAM.
Completed results and images survive restart. Interrupted jobs are marked
failed and must be rerun. Cancellation is cooperative between pipeline steps;
an already running model request completes or times out before cancellation
finishes. Closing the browser does not cancel a job.

Delete an analysis and its upload using the UI when finished. Deleting a job
removes its normalized images/reports/audit trail; deleting its original upload
is a separate operation. The UI performs both when possible. There is no
automatic expiry or backup deletion. A configured state directory must be
private to the service account; generated state directories use owner access.
Reports and uploads can still contain sensitive information. Docker Compose
persists state in the `medcheck-state` volume. Removing the container alone
does not delete that volume.

Resource defaults: 512 MiB per upload and aggregate DICOM input, 128 million
decoded pixels per study, 20 stored jobs/uploads, one job worker. Allowed server
paths are restricted to `MEDCHECK_DATA_ROOT`; symlinks outside it are refused.
ZIP traversal, symlink members, member count and expansion are checked.

## Review, comparison and exports

Each finding can be confirmed, rejected or edited, with a note and before/after
history. This records user actions without authenticating professional identity;
it never marks a clinical report verified. Editing a finding does not regenerate
the model's original summary. JSON retains full history; HTML/PDF show review
annotations. The report comparison matches structure names in a supplied UTF-8
reference report and presents relevant passages for review. It is lexical, not
a clinical agreement/contradiction detector; negation and synonyms require review.

FHIR R4 DiagnosticReport contains preliminary Observation resources and an
embedded JSON report. DICOM Basic Text SR is PARTIAL, UNVERIFIED and PRELIMINARY.
These are research exports, not a certified PACS or electronic health record integration or a claim of
full receiver-specific conformance. Format round trips are tested; validate
against the intended receiving system before integration.

## API outline

- `POST /api/upload`: multipart `file`; returns an opaque `source`.
- `POST /api/inspect`: `{source}`; returns study IDs, series and warnings.
- `POST /api/preview`: analysis options; no inference or transmission.
- `POST /api/analyze`: returns HTTP 202 with job ID.
- `GET /api/jobs/{id}`: status/progress/error/result.
- `POST /api/jobs/{id}/cancel`: request cooperative cancellation.
- `GET /api/jobs/{id}/images/{series_index}/{slice_index}`: normalized PNG.
- `PATCH /api/jobs/{id}/findings/{index}`: review status, optional edit and note.
- `GET /api/jobs/{id}/report?format=json|html|pdf|fhir|dicom-sr`.
- `DELETE /api/jobs/{id}` and `DELETE /api/uploads/{upload_id}`: explicit cleanup.

See `/docs` for request schemas. Evaluation and regression checking are described
in [evaluation.md](evaluation.md).

## Development verification

```bash
uv sync --extra dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src/medcheck
uv run bandit -r src/medcheck -ll -q
uv run pytest tests --cov=medcheck --cov-fail-under=85
```

The real browser journey is in `tests/browser/web_user_journey.py`. Start a server
on port 8765, install Playwright Chromium, then run:

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python tests/browser/web_user_journey.py
```

Pass `--api-key` when your test server requires one. Use only a dedicated test
server: the script uploads synthetic images and exercises deletion. Real upload,
analysis, viewer and downloads use the backend; deterministic cancellation,
connection recovery and finding-edit scenarios explicitly mock API responses.
Backend integration tests separately exercise real cancellation and review
persistence. CI runs both layers. The optional ResNet test uses seeded random
weights and never downloads model weights; it runs when local-models is installed.
