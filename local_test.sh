#!/usr/bin/env bash
# Dev mode: API on :8080 (auto-reload), Vite on :4000 proxying /api. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"
trap 'kill 0' EXIT
python -m uvicorn superteacher.main:app --reload --port 8080 &
(cd web && npm run dev) &
wait
