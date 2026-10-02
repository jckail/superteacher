#!/usr/bin/env bash
# Managed synthetic local demo; cleanup stops only its owned server groups.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 scripts/dev.py "$@"
