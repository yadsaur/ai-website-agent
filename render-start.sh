#!/usr/bin/env bash
set -e

echo "Starting AI Website Agent on Render..."
echo "Working directory: $(pwd)"
echo "Python version: $(python --version 2>&1)"
echo "PORT: ${PORT:-unset}"

python - <<'PY'
import os
import traceback

print("DATABASE_URL configured:", bool(os.environ.get("DATABASE_URL")))
print("BASE_URL:", os.environ.get("BASE_URL", ""))

try:
    import backend.main  # noqa: F401
    print("backend.main import check: ok")
except Exception:
    print("backend.main import check: failed")
    traceback.print_exc()
    raise
PY

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-10000}"
