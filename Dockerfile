# === Base ===
FROM python:3.13-slim AS base
WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
COPY src/ src/
COPY workflows/ workflows/

# === Lite (cloud APIs only, ~500MB) ===
FROM base AS lite
RUN uv sync --no-dev --no-cache
EXPOSE 8080
ENV MEDCHECK_HOST=0.0.0.0
ENV MEDCHECK_PORT=8080
CMD ["uv", "run", "medcheck", "serve"]

# === Full (with local ML models, ~10GB) ===
FROM base AS full
RUN uv sync --no-dev --extra local-models --no-cache
EXPOSE 8080
ENV MEDCHECK_HOST=0.0.0.0
ENV MEDCHECK_PORT=8080
CMD ["uv", "run", "medcheck", "serve"]
