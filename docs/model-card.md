# Model Card — MedCheck

MedCheck combines image processing, optional feature extraction and third-party
vision models. It does not train a diagnostic model. Its outputs are unvalidated
research artifacts; see [Intended Use](intended-use.md).

## System overview

- **Import and preparation:** DICOM files, folders, ZIP and DICOMDIR media; study
  and series UID grouping; geometry checks; normalized image volumes.
- **Privacy processing:** optional metadata allow-listing, UID remapping and
  known-identifier text removal. Optional OCR and explicit rectangles can mask
  pixels. None guarantees anonymous pixels or free text.
- **Local statistics:** relative within-series image differences and quality
  checks. The browser uses a statistical backend without model downloads.
  Optional ResNet features use generic image weights, not a medical classifier.
- **Vision:** selected images and supplied context are sent to the chosen cloud
  provider with consent, or to an explicitly configured loopback vision server.
- **Reports:** JSON, HTML, PDF, preliminary FHIR DiagnosticReport and unverified
  DICOM SR. Findings may include validated references to selected images,
  limitations, analysis provenance and review history.

## Model configuration

| Provider | Model selection | Execution |
|---|---|---|
| Claude | `MEDCHECK_CLAUDE_MODEL` | Anthropic API; optional SDK and API key |
| OpenAI | `MEDCHECK_OPENAI_MODEL` | OpenAI API; optional SDK and API key |
| Gemini | `MEDCHECK_GEMINI_MODEL` | Google Gen AI SDK and API key |
| Local | `MEDCHECK_LOCAL_MODEL` | User-managed OpenAI-compatible loopback server |

No vision weights are bundled. MedCheck does not establish the accuracy of a
provider or model. Operators control the local server and must ensure it performs
local inference rather than forwarding data. Its availability probe verifies
that the selected model is listed; it cannot prove vision capability. See
[Models](models.md) for installation and the endpoint contract.

## Provenance and review

Reports record analysis settings and, for vision runs, model/provider identifiers,
prompt version and selected/omitted image information. Finding references are
checked against the supplied image set. A valid reference only establishes that
an image was supplied; it does not verify the finding.

Review actions record before/after finding values, time and notes. Confirming or
editing a finding does not convert an export into a verified clinical report.
Reference-report comparison is local text comparison, not semantic adjudication
of which report is correct.

## Evaluation

No clinical sensitivity, specificity, calibration or subgroup performance has
been established. Software tests check parsing, geometry handling, provider
contracts, security controls and workflow behavior, not clinical correctness.

The [evaluation utility](evaluation.md) compares saved report labels with
independently supplied reference labels, with aggregate and subgroup regression
checks. It does not provide a validated dataset, generate ground truth, assess
free-text correctness or establish generalization.

LLM confidence is an **uncalibrated model self-assessment**, not a probability of
correctness. Image scores are relative comparisons within a series, not disease
probabilities, and should not be compared as calibrated severity across studies.

## Known limitations

- Vision models can fabricate findings, omit abnormalities and express high
  confidence in incorrect output. Clamping scores cannot detect these errors.
- Image selection is bounded; omitted slices can contain relevant information.
- Normalization and 2D slices do not reproduce a complete clinical imaging review.
- Geometry warnings, unsupported encodings or inconsistent dimensions may leave
  series unavailable; these limitations must remain visible in the report.
- No performance guarantees exist across anatomy, demographics, scanner vendors
  or acquisition protocols.
- Metadata filtering, identifier replacement and OCR can miss identifying data.
  Source uploads and saved artifacts remain sensitive even after processing.
- Operator cost estimates are not billing guarantees; retries may incur cost.

## Controls

Cloud transmission requires explicit consent and independent pixel review.
Unavailable cloud providers are not silently replaced with another cloud
provider. Local transport rejects remote endpoints, redirects and environment
proxies. Requests use bounded timeouts and retry policies. Reports preserve
limitations and research disclaimers; exports remain preliminary/unverified.

These controls reduce specific software and data-handling risks. They do not
establish clinical safety or authorization for diagnostic use.

## Feedback

Report software issues through the project issue tracker and sensitive findings
through [SECURITY.md](../SECURITY.md).
