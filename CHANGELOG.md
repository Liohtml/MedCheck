# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `MEDCHECK_MAX_VISION_IMAGES` (default 12) caps the total slice images sent to the
  LLM per analysis, and `MEDCHECK_MAX_DOWNLOAD_BYTES` (default 2 GiB) caps the
  easyRadiology exam-ZIP download size

### Changed
- Vision analysis now bounds the total number of slice images sent to the LLM
  across all series (previously 5 per series with no global cap), limiting cost,
  latency, and patient-data egress (#115)
- ML feature-extractor singleton is now initialized under a lock (double-checked
  locking), so concurrent requests under the web server can't build it twice (#94)
- `medcheck serve` now reads `MEDCHECK_HOST` / `MEDCHECK_PORT` (via Typer `envvar`)
  when the corresponding flag is omitted, so the Docker image's `ENV MEDCHECK_HOST=0.0.0.0`
  actually takes effect and the container is reachable from the host (#105)
- `POST /api/analyze` now returns `501 Not Implemented` instead of `200 OK` for the
  not-yet-wired pipeline stub, so clients and health checks can detect it (#96)
- `load_anatomy_instructions` uses a bounded `@lru_cache(maxsize=64)` instead of an
  unbounded `@cache`, preventing memory growth from arbitrary request-supplied
  `anatomy` values (#102)

### Fixed
- Cap `numpy<2.5` so the dependency stays compatible with the project's declared
  Python floor (`>=3.10`); numpy 2.5 requires Python 3.12 and its type stub uses
  3.12-only syntax that broke `mypy --python-version 3.10` in CI
- `medcheck analyze` now validates `--report` and `--lang`: an unknown value fails
  fast with a clear error instead of silently producing a JSON report (#99). The
  `POST /api/analyze` `language` field now also accepts `fr`/`es`, matching the CLI
  and the shipped i18n catalogs (previously only `en`/`de` passed validation)

### Security
- i18n `_load_catalog()` now constrains the language code to a safe pattern before
  building a file path, so an unvalidated CLI `--lang` value can't be interpolated
  into a path outside the i18n directory (defense-in-depth) (#106)
- easyRadiology exam-ZIP downloads are now size-capped (Content-Length check plus a
  streamed-byte limit), preventing a tampered/compromised portal response from
  exhausting disk via an unbounded body (#74)

## [0.2.1] - 2026-06-11

First published release. (The `0.2.0` tag failed to publish because the release
workflow referenced a non-existent `setup-uv@v8`; nothing was uploaded to PyPI or
GHCR under `0.2.0`. This release supersedes it and adds the changes below.)

### Added
- Internationalized reports: German, French, and Spanish report localization via
  per-language JSON catalogs in `medcheck/i18n/` with a cached loader and English
  fallback; PDF/HTML reports use localized headings, labels, and disclaimer (#16)
- `docs/intended-use.md` — intended use, dual-track positioning, and the explicit
  do/don't boundary that keeps MedCheck on the non-device side of FDA/EU MDR rules
- `docs/model-card.md` — system model card documenting components, limitations,
  and known risks (hallucination, no clinical validation, PHI handling)

### Fixed
- Release workflow pinned `setup-uv` to the non-existent `@v8`, aborting the build
  before any publish step; corrected to `@v7` to match `ci.yml`

## [0.2.0] - 2026-06-11

First release since the initial `v0.1.0`, bundling a sweep of security hardening,
reliability fixes, and new capabilities across 18 merged changes.

### Added
- `medcheck providers` command to list registered data providers
- `medcheck models` command to list LLM providers, default models, and availability
- `abdomen` anatomy hint for vision analysis prompts
- Optional `MEDCHECK_API_KEY` API-key auth for `/api` endpoints (`X-API-Key` header)
- `LocalLLMProvider` stub so the advertised offline `local` provider degrades
  gracefully instead of crashing the pipeline (full LLaVA-Med tracked in #18)
- Consent gate for external LLM transmission: `--allow-cloud-llm` flag,
  `MEDCHECK_ALLOW_EXTERNAL_LLM` env var, and an interactive confirmation prompt
- Pydantic request schema (`AnalyzeRequest`) with validation for `POST /api/analyze`
- Detailed anatomy prompt templates for hip, ankle/foot, and wrist (#10, #11, #12),
  with matching `detect_anatomy()` keyword support
- LLM API calls now have a configurable timeout (`MEDCHECK_LLM_TIMEOUT`) and
  automatic retry with exponential backoff (`MEDCHECK_LLM_RETRIES`); failures
  surface as a clear `LLMProviderError` instead of crashing the pipeline

### Changed
- Vision analysis now loads detailed anatomy templates from `prompts/anatomy/*.txt`
  (knee/shoulder/spine), falling back to built-in hints when no template exists
- Web server now binds to `127.0.0.1` by default instead of `0.0.0.0`; expose on
  the network only via an explicit `MEDCHECK_HOST=0.0.0.0`
- htmx is now vendored locally (`/static/htmx.min.js`) instead of loaded from a
  CDN, with a Subresource Integrity hash; works in air-gapped deployments
- Docker images now run as a non-root `medcheck` user
- LLM model IDs are now overridable via `MEDCHECK_CLAUDE_MODEL` /
  `MEDCHECK_OPENAI_MODEL` / `MEDCHECK_GEMINI_MODEL`; default Claude model updated
  to `claude-opus-4-8` (#68)

### Deprecated

### Removed

### Fixed
- `MEDCHECK_LLM_PROVIDER` (and the documented default) is now honoured by the
  `analyze` command instead of silently falling back to the offline `local`
  provider when no `--model` is given (#73)
- Malformed/hallucinated LLM findings are now validated, type-coerced, and
  confidence-clamped to `[0, 1]` instead of crashing the pipeline or rendering
  fabricated high-confidence findings (#71)
- README/docs/web UI model references updated from the non-existent
  `claude-opus-4-7` to `claude-opus-4-8` (#68, #69)
- easyRadiology `authenticate()` no longer requires a date of birth: DOB is not
  used or verified by this client, so gating on it implied a protection that did
  not exist. Authentication is based on the access code (#31)
- Vision prompts now use the detailed anatomy templates that were previously
  shipped but never loaded
- README "Report Bug" link now points to the correct `bug_report.yml` template
- Offline mode no longer raises `RuntimeError: No LLM provider available`; the
  `local` fallback is now a registered (unavailable) provider

### Security
- Validate the easyRadiology `linkToERI` download URL (HTTPS + host allowlist,
  redirects disabled) to prevent SSRF via a tampered portal response
- Default localhost binding and optional API key reduce unauthenticated exposure
  of patient imaging endpoints
- Patient-derived data is no longer sent to external cloud LLM APIs without
  explicit consent
- Patient names are no longer logged to stdout; a non-reversible hash of the
  patient ID is logged instead
- Portal access codes are no longer echoed into `ValueError` messages

[Unreleased]: https://github.com/Liohtml/MedCheck/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/Liohtml/MedCheck/compare/v0.1.0...v0.2.1
[0.2.0]: https://github.com/Liohtml/MedCheck/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Liohtml/MedCheck/releases/tag/v0.1.0
