#!/usr/bin/env sh
set -eu

# Run DB migrations (idempotent). Don't fail startup if migration errors —
# the app may still serve cached/static content while we investigate.
python -m backend.init_db || echo "WARNING: backend.init_db failed; continuing startup"

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"