#!/usr/bin/env bash
# Install the official ONNX Runtime 1.28.0 SDK for CI and acceptance jobs.
# Downloads Microsoft release artifacts (not a source build). Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORT_VERSION="${ORT_VERSION:-1.28.0}"
ARCH_ARG="host"
PREFIX_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage: install-onnxruntime.sh [--arch host|x64|aarch64] [--prefix DIR]

Installs official onnxruntime 1.28.0 Linux SDK artifacts from GitHub releases.
Writes VERSION.txt, verifies SHA-256, and fails on arch/version mismatch.

Environment:
  ORT_VERSION                 Pinned product version (default: 1.28.0)
  PERCEPTSHIFT_ORT_ROOT       Exported when the artifact matches this Linux host
  ORT_PREFIX                  Alias of PERCEPTSHIFT_ORT_ROOT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)
      ARCH_ARG="${2:-}"
      shift 2
      ;;
    --prefix)
      PREFIX_OVERRIDE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      ARCH_ARG="$1"
      shift
      ;;
  esac
done

map_ort_arch() {
  case "$1" in
    host|"")
      map_ort_arch "$(uname -m)"
      ;;
    x86_64|amd64|x64|X64)
      echo x64
      ;;
    aarch64|arm64|ARM64)
      echo aarch64
      ;;
    *)
      echo "unsupported ONNX Runtime architecture: $1" >&2
      exit 1
      ;;
  esac
}

ORT_ARCH="$(map_ort_arch "$ARCH_ARG")"
ASSET="onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}.tgz"
URL="https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/${ASSET}"
PREFIX="${PREFIX_OVERRIDE:-$ROOT/.cache/onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}}"
CACHE_DIR="$(dirname "$PREFIX")"
TGZ="$CACHE_DIR/${ASSET}"

# Official GitHub release asset digests for v1.28.0 (api.github.com digest field).
expected_sha() {
  case "$1" in
    onnxruntime-linux-x64-1.28.0.tgz)
      echo a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407
      ;;
    onnxruntime-linux-aarch64-1.28.0.tgz)
      echo e15ff8b5d85afe6c144d97c6fd432254bf76a219daaf17658087d6ecb3e8f0bb
      ;;
    *)
      echo ""
      ;;
  esac
}

EXPECTED_SHA="$(expected_sha "$ASSET")"
if [[ -z "$EXPECTED_SHA" ]]; then
  echo "No pinned SHA-256 for $ASSET (ORT_VERSION=$ORT_VERSION)" >&2
  exit 1
fi

mkdir -p "$CACHE_DIR"

header_ok() {
  [[ -f "$PREFIX/include/onnxruntime_cxx_api.h" ]] || \
    [[ -f "$PREFIX/include/onnxruntime/onnxruntime_cxx_api.h" ]]
}

lib_ok() {
  [[ -e "$PREFIX/lib/libonnxruntime.so" ]] || \
    [[ -e "$PREFIX/lib/libonnxruntime.so.1" ]] || \
    [[ -e "$PREFIX/lib/libonnxruntime.dylib" ]]
}

version_ok() {
  local recorded=""
  if [[ -f "$PREFIX/VERSION.txt" ]]; then
    recorded="$(tr -d '[:space:]' <"$PREFIX/VERSION.txt")"
  elif [[ -f "$PREFIX/VERSION_NUMBER" ]]; then
    recorded="$(tr -d '[:space:]' <"$PREFIX/VERSION_NUMBER")"
  fi
  [[ "$recorded" == "$ORT_VERSION" ]]
}

verify_elf_arch() {
  local so=""
  so="$(find "$PREFIX/lib" -maxdepth 1 \( -name 'libonnxruntime.so' -o -name 'libonnxruntime.so.*' \) -print -quit)"
  if [[ -z "$so" ]]; then
    echo "ONNX Runtime shared library missing under $PREFIX/lib" >&2
    exit 1
  fi
  python3 - "$so" "$ORT_ARCH" <<'PY'
import pathlib, struct, sys
path = pathlib.Path(sys.argv[1])
want = sys.argv[2]
data = path.read_bytes()[:64]
if data[:4] != b"\x7fELF":
    raise SystemExit(f"{path} is not ELF")
machine = struct.unpack_from("<H", data, 18)[0]
# EM_X86_64=62, EM_AARCH64=183
expected = 62 if want == "x64" else 183
if machine != expected:
    raise SystemExit(f"{path} ELF e_machine={machine} does not match {want} ({expected})")
print(f"ELF arch ok: {path} e_machine={machine}")
PY
}

if header_ok && lib_ok && version_ok; then
  echo "ONNX Runtime $ORT_VERSION already present at $PREFIX"
else
  if [[ -d "$PREFIX" ]] && { header_ok || lib_ok; } && ! version_ok; then
    echo "Refusing to reuse $PREFIX: version does not match pinned $ORT_VERSION" >&2
    exit 1
  fi
  echo "Downloading $ASSET"
  curl -fsSL "$URL" -o "$TGZ"
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA="$(sha256sum "$TGZ" | awk '{print $1}')"
  else
    ACTUAL_SHA="$(shasum -a 256 "$TGZ" | awk '{print $1}')"
  fi
  if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "SHA-256 mismatch for $ASSET" >&2
    echo "  expected $EXPECTED_SHA" >&2
    echo "  actual   $ACTUAL_SHA" >&2
    exit 1
  fi
  EXTRACT="$CACHE_DIR/ort-extract-$$"
  rm -rf "$EXTRACT" "$PREFIX"
  mkdir -p "$EXTRACT"
  tar -xzf "$TGZ" -C "$EXTRACT"
  INNER="$EXTRACT/onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}"
  if [[ ! -d "$INNER" ]]; then
    echo "Unexpected archive layout in $ASSET" >&2
    ls -la "$EXTRACT" >&2
    exit 1
  fi
  mv "$INNER" "$PREFIX"
  rm -rf "$EXTRACT"
  echo "$ORT_VERSION" >"$PREFIX/VERSION.txt"
fi

if ! header_ok; then
  echo "ONNX Runtime headers missing under $PREFIX/include" >&2
  exit 1
fi
if ! lib_ok; then
  echo "ONNX Runtime library missing under $PREFIX/lib" >&2
  exit 1
fi
if ! version_ok; then
  echo "ONNX Runtime version file does not record $ORT_VERSION" >&2
  exit 1
fi
verify_elf_arch

HOST_ARCH="$(map_ort_arch "$(uname -m)")"
HOST_OS="$(uname -s)"
export PERCEPTSHIFT_ORT_ROOT_INSTALLED="$PREFIX"

if [[ "$HOST_OS" == "Linux" && "$HOST_ARCH" == "$ORT_ARCH" ]]; then
  LINK="$ROOT/.cache/onnxruntime"
  mkdir -p "$ROOT/.cache"
  if [[ -L "$LINK" || ! -e "$LINK" ]]; then
    ln -sfn "$PREFIX" "$LINK"
  fi
  export PERCEPTSHIFT_ORT_ROOT="$PREFIX"
  export ORT_PREFIX="$PREFIX"
  NEW_LD_LIBRARY_PATH="${PREFIX}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export LD_LIBRARY_PATH="$NEW_LD_LIBRARY_PATH"
  if [[ -n "${GITHUB_ENV:-}" ]]; then
    {
      echo "PERCEPTSHIFT_ORT_ROOT=$PREFIX"
      echo "ORT_PREFIX=$PREFIX"
      echo "LD_LIBRARY_PATH=$NEW_LD_LIBRARY_PATH"
    } >>"$GITHUB_ENV"
  fi
fi

echo "ONNX Runtime $ORT_VERSION ($ORT_ARCH) ready at $PREFIX"
echo "PERCEPTSHIFT_ORT_ROOT=${PERCEPTSHIFT_ORT_ROOT:-}"
echo "ORT_PREFIX=${ORT_PREFIX:-}"
