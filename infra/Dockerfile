# RNF-04: one image for both Compose services: the one-shot `warehouse` (CVM load + dbt build)
# and the read-only `api` (uvicorn). Base image pinned to a patch release; runs as a non-root user.
FROM python:3.11.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DUCKDB_PATH=/app/data/warehouse.duckdb

WORKDIR /app

# Dependencies first (cached layer), then the code. The versions are bounded in pyproject.toml.
COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[dbt]"

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown app:app /app/data
COPY --chown=app:app dbt ./dbt
COPY --chown=app:app scripts ./scripts

USER app
# dbt packages resolved at build time (dbt/package-lock.yml), so the containers need no Hub access.
RUN dbt deps --project-dir dbt --profiles-dir dbt

EXPOSE 8000
CMD ["uvicorn", "fundos_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
