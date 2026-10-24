#!/usr/bin/env bash
# Regenerate requirements.lock (hash-pinned, resolved for every platform) from requirements.txt.
# Run after editing requirements.txt; pass --upgrade to pick up new releases within the ranges
# (the scheduled .depot/workflows/lock-refresh.yml does). Review the diff, then run the tests.
set -euo pipefail
cd "$(dirname "$0")/.."
uv pip compile requirements.txt --universal --python-version 3.12 --generate-hashes -o requirements.lock "$@"
echo "requirements.lock updated: $(grep -cE '^[A-Za-z0-9_.-]+==' requirements.lock) pinned packages"
