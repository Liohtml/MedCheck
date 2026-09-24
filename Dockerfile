# === Base ===
FROM python:3.14-slim AS base
WORKDIR /app

# Create an unprivileged user to run the application (avoid running as root).
RUN groupadd --system --gid 10001 medcheck \
 && useradd --system --uid 10001 --gid medcheck --home-dir /app medcheck

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

# README and LICENSE are referenced by pyproject metadata (readme/license), so
# they must be present for `uv sync` to build the medcheck package itself.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
COPY workflows/ workflows/

# === Lite (cloud APIs only, ~500MB) ===
FROM base AS lite
RUN uv sync --no-dev --extra cloud --locked --no-cache \
 && mkdir -p /app/.medcheck \
 && chown -R medcheck:medcheck /app
EXPOSE 8080
ENV MEDCHECK_HOST=0.0.0.0
ENV MEDCHECK_PORT=8080
USER medcheck
CMD ["/app/.venv/bin/medcheck", "serve"]

# === Full (with local ML models, ~10GB) ===
FROM base AS full
RUN uv sync --no-dev --extra cloud --extra local-models --locked --no-cache \
 && mkdir -p /app/.medcheck \
 && chown -R medcheck:medcheck /app
EXPOSE 8080
ENV MEDCHECK_HOST=0.0.0.0
ENV MEDCHECK_PORT=8080
USER medcheck
CMD ["/app/.venv/bin/medcheck", "serve"]
