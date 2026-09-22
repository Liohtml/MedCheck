# LLM providers and local vision

MedCheck supports Claude, OpenAI, Gemini and a user-managed local vision server.
Model output and confidence scores are not clinically validated. Provider or model
selection does not establish diagnostic accuracy.

## Installation

Install only the SDKs you need:

```bash
uv sync --extra claude
uv sync --extra openai
uv sync --extra gemini
# Or install all cloud SDKs:
uv sync --extra cloud
```

Both Docker targets install the cloud SDK bundle. `full` additionally installs
PyTorch/torchvision for image feature extraction; it does **not** bundle a vision
language model. Cloud availability requires both an installed SDK and an API key.
The availability check does not validate credentials with the remote service.
Gemini uses the maintained [Google Gen AI SDK](https://googleapis.github.io/python-genai/).

## Configuration

| Provider selection | API key | Model override |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | `MEDCHECK_CLAUDE_MODEL` |
| `openai` | `OPENAI_API_KEY` | `MEDCHECK_OPENAI_MODEL` |
| `gemini` | `GOOGLE_API_KEY` | `MEDCHECK_GEMINI_MODEL` |
| `local` | None | `MEDCHECK_LOCAL_MODEL` (required) |

Set `MEDCHECK_LLM_PROVIDER` to the desired provider name. Model identifiers are
provider-specific and should be checked against the account's available models.
Timeout is controlled with `MEDCHECK_LLM_TIMEOUT` (seconds, default 120); transient
request retries with `MEDCHECK_LLM_RETRIES` (default 2). MedCheck does not silently
switch from one cloud provider to another.

## Local vision setup

Run an OpenAI-compatible server with a vision-capable model you have installed
and selected yourself. Configure its loopback IP address and exact model ID:

```bash
export MEDCHECK_LLM_PROVIDER=local
export MEDCHECK_LOCAL_URL=http://127.0.0.1:11434/v1
export MEDCHECK_LOCAL_MODEL=your-installed-vision-model
```

The server must expose `GET /v1/models` and `POST /v1/chat/completions`, supporting
base64 PNG `image_url` message parts. Availability verifies the configured model
appears in the server's models list; that listing cannot prove image support.
An incompatible model will fail at inference. No models are downloaded or servers
started by MedCheck. Local vision works without the `local-models` extra, which is
only needed for the separate PyTorch feature extractor.

Only literal loopback IP addresses are accepted (`127.0.0.1` or `::1`); hostnames,
remote endpoints, credentials in URLs, redirects and environment proxies are
rejected or disabled. The local server remains user-managed: configure it for
local inference, since MedCheck cannot establish whether it relays data elsewhere.
Inside Docker, loopback means the container itself. Run the model server in the
same network namespace; a remote host or `host.docker.internal` is deliberately
not accepted as a local provider.

## Privacy tools and cost

`uv sync --extra privacy` installs the optional `pytesseract` Python wrapper.
OCR also needs the separately installed Tesseract executable; installing the
extra does not install it. Review de-identification and the selected images
before permitting cloud transmission.

Prices vary by selected model, image processing and token usage. Consult the
provider's published pricing and your account usage. Static per-study prices or
accuracy rankings are not supplied because they would imply precision that the
project has not measured.
