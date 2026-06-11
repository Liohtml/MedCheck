# Intended Use & Positioning

This document states what MedCheck **is** and **is not**, and the boundary the
project deliberately stays on the safe side of. It exists so contributors, users,
and reviewers share one understanding of scope — and so a well-meaning feature
doesn't quietly turn MedCheck into something it must not be.

> **MedCheck is a research and educational tool. It is NOT a medical device, is
> NOT cleared or approved by any regulator (FDA, CE/EU MDR, BfArM, or otherwise),
> and must NOT be used to diagnose, screen for, or rule out any condition.**

## Why the boundary is strict

Regulators classify software by its **intended use and actual function**, not by
the disclaimer attached to it:

- **United States (FDA).** The 21st Century Cures Act "Clinical Decision Support"
  carve-out only applies if the software, among other criteria, does **not
  acquire, process, or analyze a medical image**, and is directed at a **health
  care professional** (not a patient). Software that analyzes an MRI fails the
  first criterion outright; patient-facing software fails the professional-user
  criterion. So image-analysis software presenting findings is a regulated
  Software-as-a-Medical-Device (SaMD).
- **European Union (MDR).** There is no equivalent carve-out. Under MDR Rule 11,
  software that provides information used for diagnostic or therapeutic decisions
  is at least Class IIa, and diagnostic imaging software is commonly Class IIb.
- **Disclaimers do not change this.** "Educational only / not a diagnosis" wording
  reduces enforcement *risk* and clarifies intent, but it does not change the
  legal classification if the function and claims are diagnostic.

MedCheck is an open-source research project with no regulatory clearance. It
therefore must not be operated, marketed, or extended as a diagnostic product.

## Two tracks

MedCheck is developed along two clearly separated tracks. Keeping them distinct is
what keeps the project on the right side of the boundary.

### 1. Research / developer track (the existing default)

For researchers, developers, and technically-skilled users exploring medical
imaging pipelines. It may run the full pipeline — local ML analysis and
Vision-LLM analysis — and produce a professional radiology-style report. Every
output carries the "not a medical device, research use, must be reviewed by a
qualified radiologist" disclaimer. **Outputs are not validated and must never be
relied upon clinically.**

### 2. Patient-education track (opt-in, in development)

A layer that helps a person **understand an existing radiologist's report** and
**prepare questions for their doctor** — explaining terminology and anatomy in
plain language. This track is built to a deliberately narrow scope.

## The do / don't boundary

**MedCheck does NOT, and contributions must not make it:**

- Tell a patient that an image or region "looks normal/fine" or
  "looks concerning/abnormal." (False reassurance is the single most-documented
  patient harm, and presenting an image-derived finding to a patient as truth
  crosses the device line.)
- Present autonomous, image-derived findings to a patient as a diagnosis,
  screening result, or rule-out.
- Replace, contradict, or "correct" a radiologist's report.
- Add findings to, or drop findings from, a source report when simplifying it.
- Invert or soften hedged clinical language (e.g. "cannot exclude malignancy").
- Make any claim of diagnostic accuracy, sensitivity, or specificity.

**MedCheck may, within the educational track:**

- Explain medical terminology and anatomy generically.
- Re-state an **existing** radiologist's report in plain language, preserving its
  meaning and uncertainty verbatim.
- Help a user formulate questions to ask their clinician.
- Surface, for a technical/research user, model output that is clearly labeled as
  unvalidated AI assistance, always paired with uncertainty and error-rate
  context, and never framed as a conclusion.

## Responsibilities of operators and contributors

- **Operators** who deploy MedCheck are responsible for the legal and ethical use
  of patient data in their jurisdiction (HIPAA/GDPR/BfASG and equivalents), for
  de-identification, and for ensuring a qualified professional reviews all output.
- **Contributors** must keep changes inside the boundary above. A change that adds
  patient-facing diagnostic claims, accuracy claims, or autonomous findings is out
  of scope regardless of how useful it seems.

## Trustworthy-AI alignment (FUTURE-AI)

MedCheck aims to align with the FUTURE-AI guiding principles for trustworthy
medical AI, and tracks the gaps honestly:

| Principle | Status |
|---|---|
| **Fairness** | No subgroup/bias evaluation has been performed. Treat all output as unvalidated across demographics. |
| **Universality** | Uses open standards (DICOM, FHIR-planned) and permissive components; not validated across scanners/protocols. |
| **Traceability** | Reports state the model used and carry disclaimers; full provenance/logging is a work in progress. |
| **Usability** | CLI + Web UI + reports; patient-education readability work is in progress. |
| **Robustness** | LLM calls have timeout + retry; no clinical robustness validation exists. |
| **Explainability** | Findings carry confidence scores and limitations; AI saliency is intentionally **not** presented to patients as ground-truth localization. |

See also the [model card](model-card.md) and [SECURITY.md](../SECURITY.md).
