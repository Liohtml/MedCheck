# Supported LLM Models

## Model table

| Model | Provider | Context window | Vision | Approx. cost (per 1 M tokens) | Notes |
|-------|----------|---------------|--------|-------------------------------|-------|
| `claude-opus-4-7` | Anthropic | 200 K | Yes | $15 in / $75 out | Best accuracy; recommended for complex cases |
| `gpt-5-5` | OpenAI | 128 K | Yes | $10 in / $30 out | Strong general performance |
| `gemini-3-5-flash` | Google | 1 M | Yes | $0.35 in / $1.05 out | Fastest; good for high-volume screening |
| `local` | On-device | varies | Yes | Free (hardware cost) | Requires `full` Docker image; no data leaves your network |

> Pricing is approximate and subject to change. Check provider pricing pages for current rates.

---

## Configuration

Set the default model in `.env` or environment variables:

```bash
MEDCHECK_DEFAULT_MODEL=claude-opus-4-7
```

Or per-request via CLI:

```bash
medcheck analyze image.dcm --anatomy knee --model gemini-3-5-flash
```

Or in a workflow YAML (see [workflows.md](workflows.md)):

```yaml
- id: analyze
  uses: analyze
  with:
    model: gpt-5-5
```

### Provider API keys

| Provider | Environment variable |
|----------|---------------------|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google | `GOOGLE_API_KEY` |
| Local | _(none required)_ |

---

## Local model setup

The `full` Docker image bundles a quantized vision-language model suitable for offline inference.

```bash
docker build --target full -t medcheck:full .
docker run -p 8080:8080 -e MEDCHECK_DEFAULT_MODEL=local medcheck:full
```

To run local inference on GPU, pass `--gpus all` to `docker run` and ensure the NVIDIA Container Toolkit is installed.

---

## Pricing comparison

For a typical batch of 100 knee MRI studies (~500 images, ~2 M tokens total):

| Model | Estimated cost |
|-------|---------------|
| `claude-opus-4-7` | ~$120 |
| `gpt-5-5` | ~$60 |
| `gemini-3-5-flash` | ~$2 |
| `local` | $0 (hardware only) |

Gemini Flash is the most cost-effective option for high-volume screening workflows. Claude Opus is recommended when diagnostic accuracy is the top priority.
