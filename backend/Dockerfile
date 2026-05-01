# Backend image: FastAPI + Celery worker target.
# Built once, used for both the web service and any one-shot CLI tasks
# (alembic, hotpot ingest-now, etc.) via `docker compose run --rm backend …`.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for psycopg2; trimmed image afterwards.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq-dev postgresql-client gcc curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first to maximize layer cache.
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install -e .

# Migrations + seed data.
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY data/ ./data/

EXPOSE 8000

# Entrypoint: run migrations, idempotently seed sources, then start uvicorn.
# `--proxy-headers` and `--forwarded-allow-ips=*` make uvicorn trust the
# X-Forwarded-* headers from the nginx gateway in front of it.
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
