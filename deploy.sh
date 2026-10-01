#!/usr/bin/env bash
# Test, build and (optionally) run the container locally. The API key is passed at runtime, never at build time.
set -euo pipefail
cd "$(dirname "$0")"
VERSION="${VERSION:-$(git rev-parse --short HEAD)}"

echo "🧪 Backend tests";  python -m pytest -q
echo "🔨 Web build";      (cd web && npm ci && npm run build)
echo "🐳 Image";          docker build -t superteacher:"$VERSION" .

if [[ "${1:-}" == "run" ]]; then
  docker run --rm -p 8080:8080 -e VERSION="$VERSION" -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -v superteacher-data:/data superteacher:"$VERSION"
fi
