#!/bin/sh
# Docker container entrypoint.
#
# Runs schema migrations and default-data bootstrap before starting the
# API server, so a freshly provisioned container comes up usable without
# any host-side intervention. Both steps are idempotent: re-running them
# on a previously-initialized DB is a no-op.
#
# Override the final command by passing arguments to `docker run` /
# `docker compose run`; this script `exec`s "$@" if any args are given,
# otherwise it falls back to the default uvicorn invocation.

set -e

echo "[entrypoint] Applying schema migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Applying default data (python -m scripts.bootstrap)..."
# Bootstrap is best-effort: a failure of one seeder shouldn't keep the
# API offline. The bootstrap CLI itself logs which seeders failed.
python -m scripts.bootstrap || echo "[entrypoint] WARNING: bootstrap reported failures (continuing)"

if [ "$#" -gt 0 ]; then
    echo "[entrypoint] Starting: $*"
    exec "$@"
else
    echo "[entrypoint] Starting: uvicorn app.main:app --host 0.0.0.0 --port 8000"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
