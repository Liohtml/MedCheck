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

### Changed
- Vision analysis now loads detailed anatomy templates from `prompts/anatomy/*.txt`
  (knee/shoulder/spine), falling back to built-in hints when no template exists

### Deprecated

### Removed

### Fixed
- Vision prompts now use the detailed anatomy templates that were previously
  shipped but never loaded
- README "Report Bug" link now points to the correct `bug_report.yml` template

### Security

[Unreleased]: https://github.com/Liohtml/MedCheck/compare/HEAD...HEAD
