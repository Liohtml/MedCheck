<div align="center">

<img src="social_preview.png" alt="MedCheck - AI-powered medical imaging analysis" width="100%">

# MedCheck

**AI-powered medical imaging analysis toolkit**

[![CI](https://github.com/Liohtml/MedCheck/actions/workflows/ci.yml/badge.svg)](https://github.com/Liohtml/MedCheck/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Liohtml/MedCheck/branch/main/graph/badge.svg)](https://codecov.io/gh/Liohtml/MedCheck)
[![PyPI](https://img.shields.io/pypi/v/medcheck)](https://pypi.org/project/medcheck/)
[![Python](https://img.shields.io/pypi/pyversions/medcheck)](https://pypi.org/project/medcheck/)
[![Docker](https://img.shields.io/badge/GHCR-medcheck-blue?logo=docker)](https://github.com/Liohtml/MedCheck/pkgs/container/medcheck)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![GitHub release](https://img.shields.io/github/v/release/Liohtml/MedCheck)](https://github.com/Liohtml/MedCheck/releases)
[![GitHub stars](https://img.shields.io/github/stars/Liohtml/MedCheck)](https://github.com/Liohtml/MedCheck/stargazers)

Analyze MRI scans with local ML models and frontier Vision-LLMs (Claude, GPT, Gemini)
and generate structured, radiology-style reports — from the CLI, a web UI, or Docker.

**[Quick Start](#quick-start)** · **[Usage](#usage)** · **[Configuration](#configuration)** · **[Docs](docs/)** · **[Contributing](#contributing)** · **[Report Bug](https://github.com/Liohtml/MedCheck/issues/new?template=bug_report.yml)**

</div>

> ⚠️ **MedCheck is a research and educational tool, NOT a medical device.** Every
> output must be reviewed by a qualified radiologist before any clinical use.
> See the full [disclaimer](#disclaimer) below.

---

## Features

- **Plug & Play Docker** — single `docker run` command, no local setup required
- **Multiple data sources** — local DICOM folders/ZIPs, easyRadiology portal links, and custom plugins
- **Local ML analysis** — on-device anomaly detection and feature extraction; no API key required (one-time model download on first use, or pre-fetch with `medcheck download-models` for offline environments)
- **Vision-LLM analysis** — Claude Opus 4.8, GPT-5.5, and Gemini 3.5 Flash (opt-in, consent-gated)
- **Privacy by default** — nothing leaves your machine without explicit consent; `--deidentify` pseudonymizes reports
- **Clinical context input** — attach symptoms, trauma history, and suspected diagnosis to guide the analysis
- **Professional reports** — structured PDF/HTML/JSON with findings tables, impression, and limitations
- **YAML workflow engine** — compose and version-control custom analysis pipelines as code
- **Web UI + CLI + REST API** — 3-step browser wizard, scriptable CLI, and an HTTP API

---

## Quick Start

### Option 1 — Docker (recommended, ~1 minute)

```bash
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=your_key_here \
  -v $(pwd)/scans:/data/scans \
  ghcr.io/liohtml/medcheck:latest
```

Open [http://localhost:8080](http://localhost:8080) and follow the 3-step wizard.

### Option 2 — pip install

```bash
pip install medcheck
medcheck serve            # web UI on http://localhost:8080
```

### Option 3 — From source

```bash
git clone https://github.com/Liohtml/MedCheck.git
cd MedCheck
uv sync
uv run medcheck serve
```

### Your first analysis (CLI)

```bash
# Fully local, no API key needed (ML analysis + JSON report):
medcheck analyze ./my-dicom-folder --steps ingest,preprocess,ml_analysis,report

# Full analysis with a cloud Vision-LLM (requires a key + explicit consent):
medcheck analyze ./my-dicom-folder \
  --model claude --allow-cloud-llm \
  --symptoms "Medial knee pain after sports injury" \
  --report pdf --lang en

# Not sure what to type? Let MedCheck ask you:
medcheck analyze ./my-dicom-folder --interactive
```

Reports land in `./output/` (they contain patient data unless you pass `--deidentify` — see [Privacy & Security](#privacy--security)).

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

1. **Ingest** — load studies from local paths, the easyRadiology portal, or third-party plugins.
2. **Preprocess** — normalize pixel values, detect anatomy/planes, build volumes.
3. **ML Analyze** — run local anomaly-detection models to find suspicious slices (no API key required).
4. **Vision AI** — send the top slices to a Vision-LLM for structured findings *(only with your consent)*.
5. **Report** — render a structured radiology-style report as PDF, HTML, or JSON.

---

## Usage

### CLI reference

```bash
medcheck analyze SOURCE [OPTIONS]   # run an analysis pipeline
medcheck serve                      # start the web UI / REST API
medcheck providers                  # list data providers
medcheck models                     # list LLM providers and availability
```

The most useful `analyze` options:

| Option | Description |
|---|---|
| `--model, -m` | LLM provider: `claude`, `openai`, `gemini`, `local` |
| `--allow-cloud-llm` | Consent to send imaging data to an external cloud LLM |
| `--deidentify` | Replace patient name/ID/DOB with a pseudonym in reports |
| `--symptoms`, `--trauma`, `--diagnosis` | Clinical context to guide the analysis |
| `--report, -r` | Report format: `pdf`, `html`, `json` |
| `--lang, -l` | Report language: `en`, `de`, `fr`, `es` |
| `--steps` | Comma-separated pipeline steps (skip what you don't need) |
| `--workflow, -w` | Run a YAML-defined pipeline instead |
| `--interactive, -i` | Prompt for missing inputs |

Run `medcheck analyze --help` for the full list.

### REST API

`medcheck serve` exposes:

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness probe (always public) |
| `POST /api/analyze` | Run an analysis (JSON body: `source`, `anatomy`, `report_format`, `language`, `allow_cloud_llm`, …) |

When `MEDCHECK_API_KEY` is set, `/api/*` requires an `X-API-Key` header. Requests
are rate-limited per client IP (`MEDCHECK_RATE_LIMIT`, default 10/min).

---

## Supported Models

| Model | Provider | Best For |
|---|---|---|
| **Claude Opus 4.8** | Anthropic | Highest diagnostic quality and reasoning depth |
| **GPT-5.5** | OpenAI | High-resolution image understanding |
| **Gemini 3.5 Flash** | Google | Speed-optimized, cost-effective batch processing |
| **LLaVA-Med** | Local | Fully offline, no API key required *(coming soon — [#18](https://github.com/Liohtml/MedCheck/issues/18))* |

Default model IDs are overridable via `MEDCHECK_CLAUDE_MODEL`, `MEDCHECK_OPENAI_MODEL`, and `MEDCHECK_GEMINI_MODEL`.

---

## Data Sources

| Source | Type | Notes |
|---|---|---|
| **Local DICOM** | Folder / ZIP | Point to any directory or ZIP of DICOM files |
| **easyRadiology** | Portal link | Authenticates with the access code from your clinic (date of birth optional) |
| **Custom providers** | Plugin | See [docs/providers.md](docs/providers.md) |

---

## Configuration

Copy `.env.example` and fill in your API keys:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | — | LLM keys (at least one for cloud Vision analysis) |
| `MEDCHECK_LLM_PROVIDER` | `claude` | Default LLM provider (`claude` \| `openai` \| `gemini` \| `local`) |
| `MEDCHECK_ALLOW_EXTERNAL_LLM` | off | Consent to external LLM transmission (`1` to enable) |
| `MEDCHECK_LANGUAGE` | `en` | Default report language |
| `MEDCHECK_HOST` | `127.0.0.1` | Bind address; set `0.0.0.0` to expose on the network |
| `MEDCHECK_PORT` | `8080` | Bind port |
| `MEDCHECK_API_KEY` | — | When set, `/api` requires an `X-API-Key` header |
| `MEDCHECK_RATE_LIMIT` | `10` | `POST /api/analyze` requests per IP per minute (`0` = off) |
| `MEDCHECK_TRUST_PROXY_HEADERS` | off | Key the rate limiter on the first `X-Forwarded-For` hop (`1` — only behind a trusted reverse proxy) |
| `MEDCHECK_MAX_VISION_IMAGES` | `12` | Max slice images sent to the LLM per analysis |
| `MEDCHECK_MAX_DOWNLOAD_BYTES` | 2 GiB | Cap on portal exam-ZIP downloads |

---

## Privacy & Security

MedCheck handles patient data (PHI), so the defaults are deliberately conservative:

- **Nothing leaves your machine without consent.** Cloud Vision analysis requires
  `--allow-cloud-llm`, `MEDCHECK_ALLOW_EXTERNAL_LLM=1`, or the interactive prompt.
  If the requested LLM provider is unavailable, MedCheck never silently reroutes
  data to a different cloud provider.
- **Reports contain PHI by default.** Pass `--deidentify` to replace patient
  name/ID/DOB with a stable pseudonym. Report files are written with owner-only
  permissions.
- **Localhost by default.** The server binds to `127.0.0.1`; network exposure
  requires an explicit opt-in and should always be combined with `MEDCHECK_API_KEY`.
- **Logs are pseudonymized**, ZIP extraction is hardened, and the web UI ships a
  strict Content-Security-Policy.

Details: [SECURITY.md](SECURITY.md) · vulnerability reports via [private advisory](https://github.com/Liohtml/MedCheck/security/advisories/new).

---

## Custom Workflows

Define analysis pipelines as YAML and commit them alongside your code:

```yaml
# workflows/full_analysis.yml
name: full_analysis
description: Complete MRI analysis with ML and Vision-LLM

steps:
  - ingest:
  - preprocess:
      normalize: true
      auto_detect_anatomy: true
  - ml_analysis:
      models: [anomaly_detection, feature_extraction]
  - vision_analysis:
      provider: claude
      clinical_context:
        symptoms: "Medial knee pain after sports injury"
        trauma: "Valgus stress, 10 days ago"
  - report:
      format: pdf
      language: en
```

Run a workflow:

```bash
medcheck analyze --source ./dicoms --workflow workflows/default.yml
```

---

## Documentation

| Topic | Link |
|---|---|
| Quickstart guide | [docs/quickstart.md](docs/quickstart.md) |
| Data providers & plugins | [docs/providers.md](docs/providers.md) |
| Workflow engine reference | [docs/workflows.md](docs/workflows.md) |
| Supported models | [docs/models.md](docs/models.md) |
| Intended use & positioning | [docs/intended-use.md](docs/intended-use.md) |
| Model card (limitations & risks) | [docs/model-card.md](docs/model-card.md) |

---

## Contributing

Contributions of every size are welcome — from typo fixes to new data providers.

**Where to start:**

- 🟢 [`good first issue`](https://github.com/Liohtml/MedCheck/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) — small, well-scoped tasks with pointers
- 🙋 [`help wanted`](https://github.com/Liohtml/MedCheck/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) — features we'd love help with (new providers, local LLaVA-Med, …)
- 🗺️ [Roadmap epic #51](https://github.com/Liohtml/MedCheck/issues/51) — validation & enhancement pipeline stages

**Dev setup:**

```bash
git clone https://github.com/Liohtml/MedCheck.git
cd MedCheck
uv sync --all-extras
pre-commit install

# Quality gates (same as CI):
uv run pytest            # tests (coverage floor: 80%)
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
uv run bandit -r src/medcheck -ll -q
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR. All pull
requests require passing CI and at least one approving review.

---

## Acknowledgments

MedCheck builds on the shoulders of excellent open-source work:

- [Stanford MRNet](https://stanfordmlgroup.github.io/competitions/mrnet/) — benchmark dataset for knee MRI analysis
- [Project MONAI](https://monai.io/) — PyTorch-based framework for medical image learning
- [pydicom](https://pydicom.github.io/) — pure-Python DICOM file I/O

---

## Disclaimer

> **MedCheck is NOT a medical device and has NOT been cleared or approved by any regulatory authority (FDA, CE/EU MDR, or otherwise). It is intended solely as a research and educational tool. It must NOT be used to diagnose, screen for, or rule out any condition. All outputs must be reviewed and verified by a qualified radiologist or licensed medical professional before use in any clinical decision-making context. Do not use MedCheck as a substitute for professional medical advice, diagnosis, or treatment.**
>
> See **[Intended Use & Positioning](docs/intended-use.md)** for the scope and the do/don't boundary, and the **[Model Card](docs/model-card.md)** for limitations and known risks.

---

## License

Distributed under the [Apache License 2.0](LICENSE).
