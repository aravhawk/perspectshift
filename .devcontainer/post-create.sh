#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "PerceptShift devcontainer post-create"
./scripts/bootstrap-ubuntu.sh --noninteractive || true

if command -v corepack >/dev/null; then
  corepack enable
  corepack prepare pnpm@9.15.0 --activate
fi

if command -v pre-commit >/dev/null; then
  pre-commit install || true
fi

./scripts/verify-repository.sh || true
echo "post-create complete"
