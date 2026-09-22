# Quick Start

## Install the checkout

```bash
git clone https://github.com/Liohtml/MedCheck.git
cd MedCheck
uv sync
uv run medcheck serve
```

Open http://localhost:8080. Upload a DICOM file or ZIP, inspect available studies,
select a study and start local analysis. Follow progress, inspect slices and
download a report. Local statistics do not generate diagnostic findings and need
no cloud account. The web application defaults to metadata de-identification.

## Docker

```bash
docker build --target lite -t medcheck:lite .
docker run --rm -p 127.0.0.1:8080:8080 \
  -v medcheck-state:/app/.medcheck medcheck:lite
```

To read server-side folders, additionally mount a source directory and configure
the allowed root:

```bash
docker run --rm -p 127.0.0.1:8080:8080 \
  -v "$PWD/scans:/data/scans:ro" \
  -v medcheck-state:/app/.medcheck \
  -e MEDCHECK_DATA_ROOT=/data/scans medcheck:lite
```

The lite target includes cloud SDKs and local image statistics. The full target
adds PyTorch/torchvision for feature extraction; neither downloads or bundles a
vision language model. State storage contains sensitive data. See
[Workbench](workbench.md) for retention and deployment settings.

## CLI

```bash
# Local DICOM file, folder, ZIP or DICOMDIR:
uv run medcheck analyze ./scans \
  --steps ingest,preprocess,ml_analysis,report --deidentify --report json

# Interactive input:
uv run medcheck analyze ./scans --interactive
```

Use `--study-uid` when the source contains multiple studies. Reports are written
to `./output/` unless `--output` is specified.

For cloud vision, install the relevant SDK and set its API key in the environment:

```bash
uv sync --extra claude
export ANTHROPIC_API_KEY=your_key
uv run medcheck analyze ./scans --model claude \
  --deidentify --allow-cloud-llm --pixels-reviewed --report pdf
```

Only confirm `--pixels-reviewed` after inspecting the images and text for
identifiers. De-identification and optional OCR cannot guarantee anonymous input.
For another provider use `--extra openai` or `--extra gemini`; `--extra cloud`
installs all three. See [Models](models.md) for a user-managed local vision server.

## Evaluate saved reports

Prepare independently labelled reference cases and run:

```bash
uv run medcheck evaluate manifest.json --output evaluation.json
```

See [Evaluation](evaluation.md) for manifest format, baseline comparisons and
limitations. These metrics measure label agreement, not clinical accuracy.
