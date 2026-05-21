<div align="center">

# MedCheck

**AI-powered medical imaging analysis toolkit**

[![CI](https://github.com/Liohtml/MedCheck/actions/workflows/ci.yml/badge.svg)](https://github.com/Liohtml/MedCheck/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Liohtml/MedCheck/branch/main/graph/badge.svg)](https://codecov.io/gh/Liohtml/MedCheck)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub release](https://img.shields.io/github/v/release/Liohtml/MedCheck)](https://github.com/Liohtml/MedCheck/releases)
[![GitHub stars](https://img.shields.io/github/stars/Liohtml/MedCheck)](https://github.com/Liohtml/MedCheck/stargazers)

</div>

MedCheck analyzes MRI scans using local ML models and frontier Vision-LLMs (Claude, GPT, Gemini) to generate professional radiology-style reports with annotated images.

---

**[Quick Start](#quick-start)** · **[Documentation](docs/)** · **[Contributing](CONTRIBUTING.md)** · **[Report Bug](https://github.com/Liohtml/MedCheck/issues/new?template=bug_report.md)**

---

## Features

- **Plug & Play Docker** — single `docker run` command, no local setup required
- **Multiple data sources** — local DICOM files, easyRadiology platform, and custom plugins
- **Local ML analysis** — on-device inference with LLaVA-Med and MONAI-based models; fully offline capable
- **Vision-LLM analysis** — frontier model support for Claude Opus 4.7, GPT-5.5, and Gemini 3.5 Flash
- **Clinical context input** — attach patient history, symptoms, and prior findings to guide report generation
- **Professional PDF/HTML reports** — annotated images with structured radiology-style findings and impressions
- **YAML workflow engine** — compose and version-control custom analysis pipelines as code
- **Generic anatomy support** — brain, spine, knee, shoulder, abdomen, and more
- **Web UI + CLI** — interactive browser dashboard and a scriptable command-line interface

---

## Quick Start

### Option 1 — Docker (recommended)

```bash
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=your_key_here \
  -v $(pwd)/scans:/data/scans \
  ghcr.io/liohtml/medcheck:latest
```

Then open [http://localhost:8080](http://localhost:8080).

### Option 2 — pip install

```bash
pip install medcheck
medcheck serve
```

### Option 3 — From source

```bash
git clone https://github.com/Liohtml/MedCheck.git
cd MedCheck
uv sync
uv run medcheck serve
```

---

## How It Works

```
┌─────────┐    ┌────────────┐    ┌────────────┐    ┌───────────┐    ┌────────┐
│  Ingest  │───▶│ Preprocess │───▶│ ML Analyze │───▶│ Vision AI │───▶│ Report │
│          │    │            │    │            │    │           │    │        │
│ DICOM /  │    │ Normalize  │    │ LLaVA-Med  │    │ Claude /  │    │ PDF /  │
│ easyRad  │    │ Resize     │    │ MONAI      │    │ GPT /     │    │ HTML   │
│ Plugins  │    │ Anonymize  │    │ Anomaly    │    │ Gemini    │    │ + PNG  │
└─────────┘    └────────────┘    └────────────┘    └───────────┘    └────────┘
```

1. **Ingest** — load studies from local paths, the easyRadiology API, or third-party plugins.
2. **Preprocess** — normalize pixel values, resize to model input dimensions, and strip PHI.
3. **ML Analyze** — run local segmentation and anomaly-detection models (no API key required).
4. **Vision AI** — send annotated slices to a frontier Vision-LLM for language-based findings.
5. **Report** — render a structured radiology report with annotated images in PDF and HTML.

---

## Supported Models

| Model | Provider | Best For |
|---|---|---|
| **Claude Opus 4.7** | Anthropic | Highest diagnostic quality and reasoning depth |
| **GPT-5.5** | OpenAI | High-resolution image understanding |
| **Gemini 3.5 Flash** | Google | Speed-optimized, cost-effective batch processing |
| **LLaVA-Med** | Local | Fully offline, no API key required |

---

## Data Sources

| Source | Type | Notes |
|---|---|---|
| **Local DICOM** | `file://` | Supports single files and directory trees |
| **easyRadiology** | REST API | Requires `EASYRAD_API_KEY` |
| **Custom providers** | Plugin | See [docs/providers.md](docs/providers.md) |

---

## Configuration

Copy `.env.example` and fill in your API keys:

```bash
cp .env.example .env
```

```dotenv
# .env.example
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
EASYRAD_API_KEY=

# Optional overrides
MEDCHECK_DEFAULT_MODEL=claude-opus-4-7
MEDCHECK_REPORT_FORMAT=pdf
MEDCHECK_PORT=8080
```

### Docker environment variables

```bash
docker run \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e MEDCHECK_DEFAULT_MODEL=claude-opus-4-7 \
  -e MEDCHECK_REPORT_FORMAT=pdf \
  ghcr.io/liohtml/medcheck:latest
```

---

## Custom Workflows

Define analysis pipelines as YAML and commit them alongside your code:

```yaml
# workflows/brain-mri-full.yml
name: brain-mri-full
description: Full brain MRI analysis with FLAIR and T1 sequences

steps:
  - name: preprocess
    op: normalize
    params:
      modality: MRI
      sequences: [FLAIR, T1]

  - name: segment
    op: local_model
    params:
      model: monai-brain-seg-v2

  - name: analyze
    op: vision_llm
    params:
      model: claude-opus-4-7
      prompt_template: prompts/neuro-radiology.txt

  - name: report
    op: render_report
    params:
      format: [pdf, html]
      include_annotations: true
```

Run the workflow:

```bash
medcheck run workflows/brain-mri-full.yml --input /data/scans/patient_001/
```

---

## Documentation

| Topic | Link |
|---|---|
| Quickstart guide | [docs/quickstart.md](docs/quickstart.md) |
| Data providers & plugins | [docs/providers.md](docs/providers.md) |
| Workflow engine reference | [docs/workflows.md](docs/workflows.md) |
| Supported models | [docs/models.md](docs/models.md) |

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

```bash
git clone https://github.com/Liohtml/MedCheck.git
cd MedCheck
uv sync
pre-commit install
pytest
```

All pull requests require passing CI and at least one approving review.

---

## Acknowledgments

MedCheck builds on the shoulders of excellent open-source work:

- [Stanford MRNet](https://stanfordmlgroup.github.io/competitions/mrnet/) — benchmark dataset for knee MRI analysis
- [Project MONAI](https://monai.io/) — PyTorch-based framework for medical image learning
- [pydicom](https://pydicom.github.io/) — pure-Python DICOM file I/O

---

> **Disclaimer**
>
> **MedCheck is NOT a medical device and has NOT been cleared or approved by any regulatory authority (FDA, CE, or otherwise). It is intended solely as a research and educational tool. All outputs must be reviewed and verified by a qualified radiologist or licensed medical professional before use in any clinical decision-making context. Do not use MedCheck as a substitute for professional medical advice, diagnosis, or treatment.**

---

## License

Distributed under the [Apache License 2.0](LICENSE).
