# YAML Workflow Reference

Workflows let you chain MedCheck steps into reproducible pipelines defined in a single YAML file. Place workflow files anywhere under the `workflows/` directory.

---

## File format

```yaml
name: string          # required — unique workflow identifier
description: string   # optional
steps:
  - id: string        # required — unique step identifier within this workflow
    uses: string      # required — step type (see Available Steps below)
    with:             # optional — step-specific configuration
      key: value
    depends_on:       # optional — list of step ids that must complete first
      - other_step_id
```

---

## Available steps

### `load`

Load images from a source.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `source` | string | — | File path, URL, or PACS reference |
| `anatomy` | string | `null` | Anatomy hint (`knee`, `shoulder`, `spine`) |

### `preprocess`

Apply standard MRI preprocessing.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `normalize` | bool | `true` | Intensity normalization |
| `denoise` | bool | `false` | Apply denoising filter |
| `slice_select` | string | `"all"` | Slice selection strategy |

### `analyze`

Run LLM-based structural analysis.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | string | `"claude-opus-4-7"` | LLM to use |
| `anatomy` | string | — | Anatomy region (required if not set in `load`) |
| `prompt_override` | string | `null` | Path to a custom system prompt |

### `validate`

Validate the analysis output against `report_schema.json`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `strict` | bool | `false` | Fail the workflow on schema violations |

### `report`

Generate a human-readable report.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | string | `"json"` | Output format: `json`, `pdf`, `html` |
| `output` | string | `"output/"` | Destination directory or file path |

---

## Examples

### Basic knee analysis

```yaml
name: knee-basic
description: Single-file knee MRI analysis with PDF report

steps:
  - id: load
    uses: load
    with:
      source: data/knee_001.dcm
      anatomy: knee

  - id: analyze
    uses: analyze
    depends_on: [load]
    with:
      model: claude-opus-4-7

  - id: report
    uses: report
    depends_on: [analyze]
    with:
      format: pdf
      output: output/knee_001_report.pdf
```

### Batch portal analysis

```yaml
name: batch-shoulder
description: Pull studies from portal and analyze in parallel

steps:
  - id: load
    uses: load
    with:
      source: https://portal.example.com/study/${STUDY_ID}
      anatomy: shoulder

  - id: preprocess
    uses: preprocess
    depends_on: [load]
    with:
      normalize: true
      denoise: true

  - id: analyze
    uses: analyze
    depends_on: [preprocess]
    with:
      model: gemini-3-5-flash

  - id: validate
    uses: validate
    depends_on: [analyze]
    with:
      strict: true

  - id: report
    uses: report
    depends_on: [validate]
    with:
      format: html
      output: output/
```
