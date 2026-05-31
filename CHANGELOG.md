# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold with `src/medcheck` package structure
- Core provider abstraction (`DataProvider` base class)
- Core LLM provider abstraction (`LLMProvider` base class)
- `pyproject.toml` with uv-managed dependencies
- Pre-commit hooks (ruff, mypy)
- GitHub Actions CI workflow
- Community files: CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, issue templates
- `medcheck providers` command to list registered data providers
- `medcheck models` command to list LLM providers, default models, and availability
- `abdomen` anatomy hint for vision analysis prompts
- Optional `MEDCHECK_API_KEY` API-key auth for `/api` endpoints (`X-API-Key` header)
- `LocalLLMProvider` stub so the advertised offline `local` provider degrades
  gracefully instead of crashing the pipeline (full LLaVA-Med tracked in #18)
- Consent gate for external LLM transmission: `--allow-cloud-llm` flag,
  `MEDCHECK_ALLOW_EXTERNAL_LLM` env var, and an interactive confirmation prompt
- Pydantic request schema (`AnalyzeRequest`) with validation for `POST /api/analyze`
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

### Deprecated

### Removed

### Fixed
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

[Unreleased]: https://github.com/Liohtml/MedCheck/compare/HEAD...HEAD
