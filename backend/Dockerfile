FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.8.13

WORKDIR /code

# Static setup first: cached no matter what changes below.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home appuser

# Dependency layer from the lockfile alone, so code edits don't rebuild it.
# Bytecode compiled at build time: the ADK import chain adds ~40s to cold
# start when compiled on boot.
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# The serving app plus alembic and scripts: the migrate job and any seeding
# run from this same image, so migrations always match the deployed revision.
# app/ last: it changes most often, and layers above it stay cached.
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY app ./app

# The venv belongs to root; the runtime user only reads it.
USER appuser

EXPOSE 8080

# Per-deploy args last: a new sha invalidates only these metadata layers.
ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}
ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

# Cloud Run injects PORT; 8080 is the local-run default.
CMD ["sh", "-c", "uv run --no-sync uvicorn app.fast_api_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
