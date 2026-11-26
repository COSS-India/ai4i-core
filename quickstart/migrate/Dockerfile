# One-shot container that creates the databases and runs every Alembic
# migration, including the seed data (roles, permissions, default admin).
# Build context: the repository root.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# The migration registry finds the repo root four levels above its own
# directory, so the files keep their repository path.
WORKDIR /repo/infrastructure/databases/migrations/postgres

COPY infrastructure/databases/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY infrastructure/databases/migrations/postgres/ /repo/infrastructure/databases/migrations/postgres/
COPY quickstart/migrate/run-migrations.sh /usr/local/bin/run-migrations

ENTRYPOINT ["bash", "/usr/local/bin/run-migrations"]
