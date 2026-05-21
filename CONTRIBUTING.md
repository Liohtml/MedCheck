# Contributing to MedCheck

Thank you for your interest in contributing to MedCheck! We welcome contributions of all kinds, from bug reports and feature requests to code changes and documentation improvements.

## Ways to Contribute

### Reporting Bugs
Found a bug? We appreciate detailed bug reports. Please use our bug report template when opening an issue.

### Requesting Features
Have an idea for a new feature? Share it with us using the feature request template. We especially encourage:
- Requests for new data providers
- Suggestions for new LLM providers
- Pipeline improvements and enhancements

### Submitting Pull Requests
Code contributions are welcome! Whether it's a bug fix, feature implementation, or documentation update, we're happy to review your work.

### Improving Documentation
Help us make MedCheck better documented. You can:
- Fix typos or clarify existing documentation
- Add examples and usage guides
- Improve API documentation

## Before You Start

**Please open an issue first** to discuss your proposed changes with the maintainers. This helps us avoid duplicate work and ensures your changes align with the project's direction.

For small changes (typo fixes, minor documentation updates), you can skip this and go straight to a PR.

## Development Setup

### Prerequisites
- Python 3.11+
- Git
- [uv](https://github.com/astral-sh/uv) package manager

### Getting Started

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/MedCheck.git
   cd MedCheck
   ```
3. Install dependencies:
   ```bash
   uv sync --all-extras
   ```
4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Code Standards

We maintain high code quality standards to ensure maintainability and reliability.

### Line Length
- Maximum 120 characters per line (enforced by Ruff)

### Type Hints
- Type hints are **required** for all public functions and methods
- Use `from typing import ...` or `from collections.abc import ...` for type annotations
- Return types must be specified

### Docstrings
- Google-style docstrings are required for all public functions, classes, and modules
- Include brief description, Args, Returns, and Raises sections
- Example:
  ```python
  def fetch_data(provider: str, query: str) -> dict:
      """Fetch medical data from the specified provider.

      Args:
          provider: Name of the data provider
          query: Search query for the data

      Returns:
          Dictionary containing the fetched data

      Raises:
          ValueError: If provider is not supported
      """
  ```

### Linting and Type Checking
- Ruff is used for code formatting and linting:
  ```bash
  uv run ruff check .
  uv run ruff format .
  ```
- MyPy is used for static type checking in strict mode:
  ```bash
  uv run mypy src/medcheck --strict
  ```

## Testing

Tests are required for all new features and bug fixes.

### Running Tests
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/medcheck --cov-report=html

# Run specific test file
uv run pytest tests/test_providers.py

# Run tests matching a pattern
uv run pytest -k "test_llm"
```

### Coverage Requirements
- Minimum coverage is 85% (`--cov-fail-under=85`)
- All new code must be covered by tests
- Aim for meaningful tests, not just coverage targets

## PR Process

### Before Submitting
1. Create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make your changes and commit them (see commit message format below)
3. Ensure all tests pass:
   ```bash
   uv run pytest
   ```
4. Ensure linting passes:
   ```bash
   uv run ruff check .
   ```
5. Ensure type checking passes:
   ```bash
   uv run mypy src/medcheck --strict
   ```
6. Push to your fork and open a pull request

### Commit Message Format
Use conventional commit format:
- `feat:` - A new feature
- `fix:` - A bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring without behavior changes
- `test:` - Adding or updating tests
- `chore:` - Build, CI, or dependency updates

Example: `feat: add support for FHIR data provider`

### Pull Request Requirements
- Link related issues: "Fixes #123" or "Closes #456"
- Clear description of changes
- At least one maintainer review is required
- All CI checks must pass
- Code coverage must not decrease

## Adding a New Data Provider

To add a new data provider for medical data sources:

1. Create a new file in `src/medcheck/providers/`:
   ```python
   # src/medcheck/providers/my_provider.py
   from medcheck.providers.base import DataProvider

   class MyDataProvider(DataProvider):
       """Provider for my medical data source."""

       name = "my_provider"

       async def fetch(self, query: str) -> dict:
           """Fetch data from the provider."""
           pass
   ```

2. Implement the `DataProvider` interface:
   - Implement required abstract methods
   - Add proper error handling
   - Include rate limiting if needed

3. Register URL patterns in the router:
   ```python
   # src/medcheck/providers/__init__.py
   url_patterns = [
       # ... existing patterns
       ("my-provider", MyDataProvider),
   ]
   ```

4. Add comprehensive tests:
   ```python
   # tests/test_providers/test_my_provider.py
   import pytest
   from medcheck.providers.my_provider import MyDataProvider

   @pytest.mark.asyncio
   async def test_fetch():
       provider = MyDataProvider()
       result = await provider.fetch("test query")
       assert result is not None
   ```

## Adding a New LLM Provider

To add a new LLM provider for language model integration:

1. Create a new file in `src/medcheck/llm/`:
   ```python
   # src/medcheck/llm/my_llm.py
   from medcheck.llm.base import LLMProvider

   class MyLLMProvider(LLMProvider):
       """LLM provider for my model."""

       name = "my_llm"

       async def generate(self, prompt: str) -> str:
           """Generate response from the LLM."""
           pass
   ```

2. Implement the `LLMProvider` interface:
   - Implement required abstract methods
   - Add proper error handling and retries
   - Implement streaming if supported

3. Add environment variable for API key:
   ```python
   import os
   api_key = os.getenv("MY_LLM_API_KEY")
   ```

4. Register the provider:
   ```python
   # src/medcheck/llm/__init__.py
   from medcheck.llm.my_llm import MyLLMProvider
   ```

5. Add comprehensive tests:
   ```python
   # tests/test_llm/test_my_llm.py
   import pytest
   from medcheck.llm.my_llm import MyLLMProvider

   @pytest.mark.asyncio
   async def test_generate():
       provider = MyLLMProvider()
       response = await provider.generate("test prompt")
       assert response is not None
   ```

## License

By contributing to MedCheck, you agree that your contributions will be licensed under the Apache License 2.0. See the LICENSE file for details.

## Questions?

If you have questions about contributing, feel free to open an issue or reach out to the maintainers. We're here to help!

Happy coding!
