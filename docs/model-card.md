# Model Card — MedCheck

MedCheck is not a single trained model; it is a **pipeline** that orchestrates
third-party models and its own heuristics. This card describes that system, its
data flow, and — most importantly — its limitations. It follows the spirit of
model cards (Mitchell et al., 2019) adapted for a multi-component tool.

> **Bottom line:** MedCheck produces **unvalidated, research-grade** output. No
> component has been clinically validated. All output must be reviewed by a
> qualified radiologist. See [intended-use.md](intended-use.md).

## System overview

```
Ingest → Preprocess → ML Analyze → Vision AI → Report
```

- **Ingest / Preprocess** — load DICOM (local files/ZIP or the easyRadiology
  portal), normalize pixel data, select representative slices. Deterministic; no
  ML.
- **ML Analyze** — local, on-device analysis (e.g. anomaly/feature heuristics).
  Runs without any API key. Not a trained diagnostic classifier.
- **Vision AI** — sends selected slices + clinical context to a **third-party
  Vision-LLM** (see below) and parses a structured response. This step is
  **gated by explicit consent** before any external transmission.
- **Report** — renders PDF/HTML/JSON with findings, confidence, limitations, and
  a mandatory disclaimer.

## Models used

MedCheck does not ship trained weights. It calls external providers chosen by the
operator:

| Provider | Model (default, overridable) | Hosting | Notes |
|---|---|---|---|
| Anthropic | `claude-opus-4-8` (`MEDCHECK_CLAUDE_MODEL`) | Cloud API | Frontier general VLM; not medical-specialized or validated. |
| OpenAI | `gpt-5.5` (`MEDCHECK_OPENAI_MODEL`) | Cloud API | Frontier general VLM. |
| Google | `gemini-3.5-flash` (`MEDCHECK_GEMINI_MODEL`) | Cloud API | Frontier general VLM. |
| Local | LLaVA-Med (planned, see [#18](https://github.com/Liohtml/MedCheck/issues/18)) | On-device | Offline path; not yet implemented. |

These are **general-purpose** models. They are not medical devices, are not
trained or tuned by MedCheck, and their medical-imaging output is known to
include hallucinations and omissions even in state-of-the-art systems.

## Intended use

Research and education only. See [intended-use.md](intended-use.md) for the full
scope and the do/don't boundary. **Not for diagnosis, screening, or rule-out.**

## Out-of-scope use

- Any clinical decision-making without independent radiologist review.
- Presenting image-derived findings to a patient as a diagnosis or reassurance.
- Use as a substitute for professional medical advice.
- Any use implying regulatory clearance — there is none.

## Training data & provenance

MedCheck trains **no models**, so it has no training data of its own. The
behavior of the Vision-LLM step is determined entirely by the third-party model
selected, whose training data and properties are controlled by that provider and
are outside MedCheck's knowledge or control.

## Evaluation

**None for clinical accuracy.** MedCheck has not been evaluated for diagnostic
sensitivity, specificity, calibration, or subgroup fairness. The test suite covers
software correctness (parsing, pipeline behavior, security controls), **not
clinical performance.** Confidence scores in reports come from the LLM's
self-reported values and are not calibrated probabilities.

## Known limitations & risks

- **Hallucination / omission.** The Vision-LLM can report findings not present in
  the image, or miss findings that are. Confidence scores may be high on
  fabricated findings. MedCheck validates and clamps these values
  ([#71](https://github.com/Liohtml/MedCheck/issues/71)) but cannot detect a
  plausible-but-wrong finding.
- **No subgroup validation.** Performance across age, sex, body habitus, scanner
  vendor, field strength, and protocol is unknown.
- **PHI handling.** Imaging data is sensitive. External transmission is
  consent-gated, and robust de-identification (including burned-in pixel PHI) is
  in progress ([#57](https://github.com/Liohtml/MedCheck/issues/57)). Operators
  remain responsible for HIPAA/GDPR compliance.
- **AI saliency is not trustworthy localization.** Saliency/heatmaps are not
  presented to patients as ground truth; published evidence shows they are
  unreliable for localization.
- **General, not medical, models.** The default Vision-LLMs are not radiology
  models and have no medical clearance.

## Mitigations in place

- Explicit consent gate before any external LLM transmission, with an offline
  path planned.
- Validation + confidence clamping of LLM-returned findings.
- Mandatory disclaimer on every report; logs pseudonymize patient identifiers.
- Configurable timeout + retry so a provider failure degrades gracefully.

## Maintainers & feedback

Issues and security reports: see [SECURITY.md](../SECURITY.md) and the project
issue tracker. This card is updated as the system evolves.
