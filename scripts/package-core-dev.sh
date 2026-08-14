#!/usr/bin/env bash
# Explicit non-release CPack core developer artifact.
# This is NOT the supported PerceptShift release package (API/ROS overlay may be absent).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${DIST_DIR:-$ROOT/dist}"
mkdir -p "$OUT_DIR"

VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION")"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
esac

echo "Packaging PerceptShift $VERSION for $ARCH as CORE-DEV (not a release artifact)"

BUILD_DIR=""
for candidate in "$ROOT/build/release-arm64" "$ROOT/build/release-x64" "$ROOT/build/release" "$ROOT/build/default" "$ROOT/build"; do
  if [[ -d "$candidate" ]]; then
    BUILD_DIR="$candidate"
    break
  fi
done

if [[ -z "$BUILD_DIR" ]]; then
  echo "No CMake build directory found; configure and build first (e.g. cmake --preset release && cmake --build --preset release)" >&2
  exit 1
fi

if ! command -v cpack >/dev/null 2>&1; then
  echo "cpack is required to produce Debian packages" >&2
  exit 1
fi

(cd "$BUILD_DIR" && cpack -G DEB)
mapfile -t DEBS < <(find "$BUILD_DIR" "$OUT_DIR" -maxdepth 2 -type f -name 'perceptshift*.deb')
if [[ "${#DEBS[@]}" -eq 0 ]]; then
  echo "ERROR: no perceptshift*.deb produced by cpack" >&2
  exit 1
fi

copied=0
for deb in "${DEBS[@]}"; do
  if [[ ! -s "$deb" ]]; then
    echo "ERROR: empty package artifact: $deb" >&2
    exit 1
  fi
  base="$(basename "$deb")"
  dest="$OUT_DIR/${base%.deb}-core-dev.deb"
  # Keep original if already named core-dev.
  if [[ "$base" == *core-dev* ]]; then
    dest="$OUT_DIR/$base"
  fi
  cp -v "$deb" "$dest"
  copied=$((copied + 1))
done

if [[ "$copied" -lt 1 ]]; then
  echo "ERROR: failed to copy Debian packages to $OUT_DIR" >&2
  exit 1
fi

echo "Core-dev artifacts in $OUT_DIR (NOT a supported release package):"
ls -la "$OUT_DIR"/perceptshift*.deb
