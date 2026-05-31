# Open-Source Options for MedCheck — Research Report

_Researched May 2026. All license claims below were verified against primary
sources (HuggingFace model cards, GitHub LICENSE files, official docs). The six
highest-stakes claims were additionally adversarially fact-checked._

MedCheck is **Apache-2.0**. The guiding rule used throughout: a dependency's
license must be permissive (Apache-2.0 / MIT / BSD / CC0) **or** interact only
over a network API so no copyleft propagates. Model **weights** are judged
separately from code — several "open" medical models ship permissive code but
**research-only weights**.

---

## TL;DR recommendations by open issue

| Issue | Recommendation | Pick |
|---|---|---|
| **#18** local vision model | **Adopt Lingshu-7B** (MIT, multi-modal incl. MRI). Keep the existing `LocalLLMProvider` stub; wire Lingshu behind the optional `local-models` extra. Avoid LLaVA-Med (research-only). | Lingshu-7B / HuatuoGPT-Vision (Apache-2.0) |
| **#25** DICOMDIR / German CDs | **Adopt** `pydicom.fileset.FileSet` + add `pylibjpeg`/`python-gdcm` for compressed pixel data. | pydicom FileSet API |
| **#13** Orthanc provider | **Adopt** via DICOMweb over HTTP — copyleft-safe. | `dicomweb-client` |
| **#14** Google Cloud Healthcare | **Adopt** — Apache-2.0 client libs, DICOMweb. | `dicomweb-client` + ADC auth |
| **#15** OHIF | **Reclassify** — it's a *viewer*, not a data provider. Point it at our DICOMweb, don't build a provider for it. | (architecture note) |
| local ML (#17 area) | **Adopt** MONAI + TorchIO; nnU-Net v2 when training. | MONAI / TorchIO |
| reporting upgrade | **Consider** FHIR DiagnosticReport export + optional DICOM SR. | `fhir.resources`, `highdicom` |

---

## 1. Local / offline vision-language models (issue #18)

The issue title says "LLaVA-Med" — but **LLaVA-Med's weights are research-only**
and must not be the default in a commercially-usable Apache-2.0 tool.

| Model | Code | Weights | MRI? | Size | Verdict |
|---|---|---|---|---|---|
| **Lingshu-7B / 32B** | MIT | **MIT** | ✅ explicit (12+ modalities incl. MRI) | 7B ≈16 GB / 32B | **ADOPT** (top pick) |
| **HuatuoGPT-Vision-7B-Qwen2.5VL** | Apache-2.0 | Apache-2.0 | general medical | ~8B ≈16 GB | **ADOPT** (alt) |
| **CheXagent-2-3b** | MIT | MIT | ❌ chest X-ray only | 3B ≈6–8 GB | Adopt only if CXR |
| **BiomedCLIP** | MIT | MIT | encoder only (no text gen) | ~200M <2 GB | Adopt for retrieval/embeddings |
| **MedGemma 4B/27B** | Apache-2.0 | **HAI-DEF custom** (commercial OK *with* restrictions) | ❌ no MRI in training | 4B ≈10 GB / 27B | Consider; ship under its own terms |
| **RadFM** | MIT | **unspecified** (no license file) | ✅ 2D+3D incl. MRI | ~14B (A100 80 GB) | Consider research; clear weights w/ authors |
| **LLaVA-Med** | MS Research | **research-only** | biomedical figures | 7B ≈16 GB | **AVOID** (commercial out of scope) |
| **Med-Flamingo** | MIT | **LLaMA-1 non-commercial** | lit. images | ~9B | **AVOID** commercial |
| **BiomedGPT** | "Apache" tag but | **non-commercial** (OFA) | incl. CXR | small | **AVOID** commercial |

**Verified flags:** LLaVA-Med's card literally states *"Any deployed use case —
commercial or otherwise — is out of scope."* MedGemma weights are HAI-DEF, **not**
Apache-2.0, and have **no MRI** in training data. Lingshu-7B is genuinely MIT and
explicitly lists MRI.

**Action for #18:** keep `LocalLLMProvider` as the stub it is today, then implement
it against **Lingshu-7B** under the optional `local-models` extra (transformers +
torch). Update the README/issue to correct "LLaVA-Med" → Lingshu (with a note on
why). This keeps MedCheck commercially clean.

## 2. Medical imaging ML / segmentation frameworks

| Framework | License | MRI | Pretrained weights | Verdict |
|---|---|---|---|---|
| **MONAI** | Apache-2.0 | strong | model-zoo bundles, per-bundle licenses | **ADOPT** (primary) |
| **TorchIO** | MIT | strong (MRI-specific augmentations) | none (IO/aug only) | **ADOPT** (complement) |
| **nnU-Net v2** | Apache-2.0 | strong | via Zenodo, per-model license | Adopt/consider when training |
| **TotalSegmentator** | **code Apache-2.0; weights mixed** | ✅ `total_mr` task is Apache-2.0 | some tasks **CC BY-NC** | **CONSIDER** — confine to Apache weights (`total_mr`); avoid NC tasks (`brain_aneurysm`, etc.) commercially |
| **FastSurfer** | Apache-2.0 | brain only; PyTorch | yes | Consider (brain); avoid FreeSurfer surface path |
| **SynthSeg** | Apache-2.0 | brain only; **TensorFlow** | yes | Consider (brain); TF stack mismatch |

**Action:** base local ML analysis on **MONAI + TorchIO** (both clean). They fit
the existing pydicom+numpy pipeline. TotalSegmentator `total_mr` is attractive for
MRI organ/structure segmentation but only adopt the Apache-2.0 weight tasks.

## 3. DICOM tooling — and DICOMDIR/CD handling (issue #25)

All MIT/Apache, all compatible:

- **pydicom** (MIT, v3.x) — already used.
- **highdicom** (MIT) — adds DICOM SR + Segmentation encoding (see §5).
- **dicomweb-client** (MIT) — QIDO/WADO/STOW; the basis for #13/#14.
- **pynetdicom** (MIT) — classic DIMSE (C-FIND/MOVE/STORE) if a PACS is in scope.
- **pylibjpeg** (MIT) + **python-gdcm** (Apache/BSD) — decode compressed Pixel
  Data (JPEG / JPEG-LS / JPEG 2000) common on real-world CDs.

**Issue #25 — reading a German clinic's MRI CD correctly.** Such CDs ship a
top-level `DICOMDIR` index plus image files in subfolders. The legacy
`read_dicomdir()` / `DicomDir` was **removed in pydicom 3.0**. Use the modern
`FileSet` API:

```python
from pydicom import dcmread
from pydicom.fileset import FileSet

ds = dcmread("/media/cd/DICOMDIR")     # a DICOMDIR is itself a DICOM dataset
fs = FileSet(ds)                        # paths resolved relative to DICOMDIR

fs.find_values("StudyDescription")      # browse the index cheaply (no pixels)
for instance in fs:                     # or fs.find(SeriesDescription="t2_tse")
    img = instance.load()               # FileDataset; .pixel_array needs a decoder
```

Robustness notes for the provider:
- Locate the `DICOMDIR` file (often uppercase, no extension) — case varies per CD.
- `FileSet` resolves references relative to the DICOMDIR, so it works mounted or copied.
- Install **pylibjpeg** and/or **python-gdcm** so `pixel_array` works on compressed CDs.
- **Fallback:** if the DICOMDIR is missing/corrupt (it happens), recursively
  `dcmread()` the files directly. The existing `LocalProvider` already scans
  directories — extend it to prefer DICOMDIR, then fall back to a recursive scan.

## 4. DICOM server / viewer providers (issues #13, #14, #15)

Build the provider abstraction around **DICOMweb (QIDO-RS query + WADO-RS
retrieve)** using MIT-licensed `dicomweb-client` — one code path serves both
Orthanc and Google Cloud Healthcare.

- **#13 Orthanc** — core **GPLv3**, DICOMweb plugin **AGPLv3**. **Copyleft-safe to
  use**: the Orthanc project explicitly states clients talking only via REST/DICOM
  incur no license obligation. ✅ Verified. *Do not* write an in-process Orthanc
  plugin from MedCheck code (that would trigger copyleft); over HTTP we're clear.
- **#14 Google Cloud Healthcare** — DICOMweb (QIDO/WADO/STOW); auth via OAuth2 ADC
  / service account; `google-cloud-healthcare` (Apache-2.0) or `dicomweb-client`
  with its GCP helpers. Free tier: 25k req/mo + 1 GB. **Adopt.**
- **#15 OHIF Viewer** — MIT, but it is a **client-side web viewer, not a data
  source**. It *consumes* the same DICOMweb backends. **Recommendation: do not
  implement OHIF as a `DataProvider`** (architectural mismatch). Instead, optionally
  offer OHIF as a *viewer* pointed at our DICOMweb endpoints. Suggest re-scoping #15.

## 5. Structured reporting standards (reporting upgrade)

- **FHIR DiagnosticReport / ImagingStudy** — spec is **CC0**; `fhir.resources`
  (BSD) or `fhirclient` (Apache-2.0). Cleanest standards alignment; add as a JSON
  export alongside the current JSON. **Consider (high value, low friction).**
- **DICOM SR (TID 1500)** via **highdicom.sr** (MIT) — machine-readable findings
  when evidence images exist. Optional export.
- **RadLex RIDs** and **RadElement CDE IDs** — reference codes in output (cheap,
  high value). Custom RSNA licenses: **attribution required, identifiers must not
  be altered, ontology not to be embedded/modified**. Reference IDs, don't bundle.
- **RSNA RadReport (MRRT)** templates — usable with attribution + naming
  conditions; good source of standardized layouts.

## 6. Public MRI datasets (testing / validation)

**Redistributable — safe as CI fixtures in the repo:**
- **pydicom-data** (MIT) — already accessible via `pydicom.data.get_testdata_file`.
- **GDCM sample data** (BSD/public-domain) — good parser edge-case fixtures.
- **TCIA CC-BY collections** — redistributable *with attribution + DOI*; must check
  the per-collection license badge (a minority are CC BY-NC or controlled).

**Research-only — must NOT be committed (validation via download + DUA only):**
- **Stanford MRNet** (knee) — Stanford RUA, non-commercial, no redistribution.
- **fastMRI** (knee/brain) — code MIT but **data** under NYU sharing agreement.
- **OAI** (knee) — NIH/NDA account required.
- **RSNA challenge datasets** — non-commercial, no redistribution (and mostly CT/CXR).

**Action:** for tests, vendor a small MR series from **pydicom-data/GDCM**; do not
attempt to ship MRNet/fastMRI/OAI. A download-script + documented DUA step is the
correct pattern for validation against those.

---

## Suggested follow-up issues / re-scoping

1. **#18** — correct "LLaVA-Med" → **Lingshu-7B** (MIT, MRI-capable); implement
   `LocalLLMProvider` behind the `local-models` extra. (License rationale above.)
2. **#25** — implement DICOMDIR support in `LocalProvider` via `FileSet` with a
   recursive-scan fallback; add `pylibjpeg`/`python-gdcm` to decode compressed CDs.
3. **#13 / #14** — single `DicomWebProvider` (using `dicomweb-client`) covering both
   Orthanc and Google Cloud Healthcare; auth strategy per backend.
4. **#15** — re-scope from "OHIF data provider" to "OHIF viewer integration pointed
   at MedCheck's DICOMweb"; OHIF is not a data source.
5. New (optional) — FHIR `DiagnosticReport` export and DICOM SR (TID 1500) export.

## Primary sources

- LLaVA-Med: https://huggingface.co/microsoft/llava-med-v1.5-mistral-7b
- MedGemma: https://huggingface.co/google/medgemma-4b-it · https://developers.google.com/health-ai-developer-foundations/terms
- Lingshu: https://huggingface.co/lingshu-medical-mllm/Lingshu-7B · https://arxiv.org/abs/2506.07044
- HuatuoGPT-Vision: https://huggingface.co/FreedomIntelligence/HuatuoGPT-Vision-7B-Qwen2.5VL
- CheXagent: https://huggingface.co/StanfordAIMI/CheXagent-2-3b
- BiomedCLIP: https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224
- RadFM: https://github.com/chaoyi-wu/RadFM
- MONAI: https://github.com/Project-MONAI/MONAI
- TorchIO: https://github.com/TorchIO-project/torchio
- nnU-Net: https://github.com/MIC-DKFZ/nnUNet
- TotalSegmentator: https://github.com/wasserth/TotalSegmentator
- pydicom FileSet: https://pydicom.github.io/pydicom/stable/tutorials/filesets.html
- highdicom: https://github.com/ImagingDataCommons/highdicom
- dicomweb-client: https://dicomweb-client.readthedocs.io/en/latest/introduction.html
- Orthanc licensing: https://orthanc.uclouvain.be/book/faq/licensing.html
- Google Cloud Healthcare DICOMweb: https://docs.cloud.google.com/healthcare-api/docs/how-tos/dicomweb
- OHIF datasources: https://docs.ohif.org/configuration/datasources/dicom-web/
- FHIR DiagnosticReport: https://www.hl7.org/fhir/diagnosticreport.html · license https://hl7.org/fhir/R5/license.html
- RadLex license: https://www.rsna.org/practice-tools/data-tools-and-standards/radlex-radiology-lexicon
- MRNet: https://stanfordmlgroup.github.io/competitions/mrnet/
- fastMRI: https://fastmri.med.nyu.edu/
- OAI: https://nda.nih.gov/oai/
- pydicom-data: https://github.com/pydicom/pydicom-data
- TCIA usage policy: https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/
