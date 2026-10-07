# AutoValor CO API image.
# Dependencies are installed from uv.lock so the image matches CI exactly.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# LightGBM's wheel links against libgomp, which the slim image does not carry. Same fix as
# Dockerfile.api, and for the same reason it went unnoticed for so long: this image was
# built in CI but never started.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: third-party dependencies only, so code changes do not invalidate them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: the project itself.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 autovalor \
    && mkdir -p /app/data /app/mlruns \
    && chown -R autovalor:autovalor /app
USER autovalor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"]

CMD ["uvicorn", "autovalor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
