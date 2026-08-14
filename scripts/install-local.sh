#!/usr/bin/env bash
# Install PerceptShift locally from a build tree or Debian packages.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/usr/local}"
FROM_PACKAGES=""

usage() {
  cat <<'EOF'
Usage: install-local.sh [--prefix DIR] [--from-packages DIR]

  --prefix DIR           Install prefix for from-source install (default: /usr/local)
  --from-packages DIR    Install *.deb packages from DIR via apt/dpkg
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift ;;
    --from-packages) FROM_PACKAGES="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [[ -n "$FROM_PACKAGES" ]]; then
  DEBS=()
  while IFS= read -r deb; do
    DEBS+=("$deb")
  done < <(find "$FROM_PACKAGES" -maxdepth 2 -name 'perceptshift*.deb' | sort)
  if [[ "${#DEBS[@]}" -eq 0 ]]; then
    echo "No perceptshift*.deb found under $FROM_PACKAGES" >&2
    exit 1
  fi
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y "${DEBS[@]}"
  else
    sudo dpkg -i "${DEBS[@]}"
  fi
  echo "Installed packages from $FROM_PACKAGES"
  exit 0
fi

# From-source layout converging on the same paths packaging uses.
cmake --install "${ROOT}/build" --prefix "$PREFIX" 2>/dev/null || \
  cmake --install "${ROOT}/build/dev-x64" --prefix "$PREFIX" 2>/dev/null || \
  cmake --install "${ROOT}/build/dev-arm64" --prefix "$PREFIX" 2>/dev/null || \
  echo "CMake install skipped (build tree missing)"

if command -v uv >/dev/null 2>&1; then
  uv tool install --from "$ROOT/python/perceptshift_cli" perceptshift 2>/dev/null || true
fi

echo "install-local.sh complete (prefix=$PREFIX)"
