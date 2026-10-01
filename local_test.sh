#!/usr/bin/env bash
# Dev mode: API on :8080 (auto-reload), Vite on :4000 proxying /api. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"
# Local dev runs without auth by default; export AUTH_PASSWORD=... (and unset AUTH_DISABLED) to test the login flow.
export AUTH_DISABLED="${AUTH_DISABLED:-$([[ -z "${AUTH_PASSWORD:-}" ]] && echo true || echo false)}"
trap 'kill 0' EXIT
python -m uvicorn superteacher.main:app --reload --port 8080 &
(cd web && npm run dev) &
wait
