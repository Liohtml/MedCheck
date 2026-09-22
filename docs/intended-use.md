# Intended Use & Positioning

MedCheck is a research and educational imaging toolkit. It has no regulatory
clearance and must not be used to diagnose, screen for or rule out a condition.
Outputs are unvalidated and must not replace qualified clinical assessment.

## Supported research use

Researchers and developers can inspect DICOM studies, investigate image quality,
compare processing configurations, experiment with vision providers and evaluate
saved report labels against independent reference annotations. The browser and
CLI support these activities with traceable settings and research reports.

Local statistics describe relative image differences; they generate no diagnostic
findings. Vision output is experimental model output. A reference-report text
comparison may help identify passages for human review but does not determine
whether either report is clinically correct.

## Boundaries

- Do not present image-derived output to a patient as a diagnosis, reassurance,
  screening result or exclusion of disease.
- Do not substitute generated text for a radiologist's report or treat an
  automated comparison as correction of that report.
- Do not claim measured clinical accuracy, sensitivity, specificity or calibrated
  confidence without an appropriate independent validation study.
- Do not interpret user review labels, FHIR formatting or DICOM SR export as
  clinical verification. Exports remain preliminary and unverified.
- Any future educational explanation of an existing clinical report must preserve
  its meaning and uncertainty and avoid introducing or dropping findings.

## Responsibilities

Operators control access, source permissions, retention, provider configuration
and authorization to process or transmit patient data. Metadata filtering and OCR
are aids, not a guarantee of anonymization. Review images and text independently
before cloud transmission; treat stored artifacts as sensitive.

Contributors should keep behavior and documentation consistent with this research
scope. A disclaimer alone does not determine the requirements for deploying a
product in a regulated setting; MedCheck does not provide such a determination.

## Current evidence and limitations

| Area | Status |
|---|---|
| Clinical performance | Not established; software tests are not clinical validation |
| Subgroups | Evaluation supports supplied subgroup labels; no demographic performance claim |
| Interoperability | DICOM input, preliminary FHIR output and unverified DICOM SR; integration must be tested with recipients |
| Traceability | Run settings, vision provenance, selected images and finding review history |
| Usability | Working browser upload, progress, cancellation, viewer, review and export workflows |
| Robustness | Input limits, error handling and provider retries; clinical robustness remains unvalidated |
| Confidence | Uncalibrated model self-assessment; relative image scores are not disease probabilities |

See the [Model Card](model-card.md), [Evaluation](evaluation.md) and
[Security Policy](../SECURITY.md) for details.
