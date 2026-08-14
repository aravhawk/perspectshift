#!/usr/bin/env bash
# Ensure CMake >= 3.28 using the distro package or an official Kitware binary.
set -euo pipefail

REQUIRED_MAJOR=3
REQUIRED_MINOR=28
CMAKE_VERSION="${CMAKE_VERSION:-3.31.8}"

cmake_new_enough() {
  command -v cmake >/dev/null 2>&1 || return 1
  python3 - <<'PY'
import shutil, subprocess, sys
cmake = shutil.which("cmake")
if not cmake:
    sys.exit(1)
out = subprocess.check_output([cmake, "--version"], text=True).splitlines()[0]
ver = out.split()[-1]
parts = [int(x) for x in ver.split(".")[:3]]
while len(parts) < 3:
    parts.append(0)
sys.exit(0 if tuple(parts) >= (3, 28, 0) else 1)
PY
}

if cmake_new_enough; then
  cmake --version | head -n 1
  exit 0
fi

echo "CMake >= 3.28 required; installing official Kitware ${CMAKE_VERSION}"
arch="$(uname -m)"
case "$arch" in
  x86_64)
    asset="cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz"
    sha="630615d8e98ac33eba7fbe472626dff5c899c85af3c024585ae109166a6909d0"
    ;;
  aarch64|arm64)
    asset="cmake-${CMAKE_VERSION}-linux-aarch64.tar.gz"
    sha="609735983e3bdf24b6ab379d918458d64196fe72b98226f62dd5e9fe7b2997cc"
    ;;
  *)
    echo "unsupported host architecture for CMake bootstrap: $arch" >&2
    exit 1
    ;;
esac

url="https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/${asset}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$url" -o "$tmp/$asset"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$tmp/$asset" | awk '{print $1}')"
else
  actual="$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')"
fi
if [[ "$actual" != "$sha" ]]; then
  echo "CMake SHA-256 mismatch for $asset" >&2
  echo "  expected $sha" >&2
  echo "  actual   $actual" >&2
  exit 1
fi

prefix="${CMAKE_INSTALL_PREFIX:-}"
if [[ -z "$prefix" ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    prefix=/usr/local
  else
    prefix="${HOME}/.local"
  fi
fi
mkdir -p "$prefix" "$tmp/extract"
tar -xzf "$tmp/$asset" -C "$tmp/extract"
inner="$(find "$tmp/extract" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
cp -a "$inner"/. "$prefix"/
export PATH="${prefix}/bin:${PATH}"
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "${prefix}/bin" >>"$GITHUB_PATH"
fi
if ! cmake_new_enough; then
  echo "CMake still below 3.28 after installing $CMAKE_VERSION" >&2
  exit 1
fi
cmake --version | head -n 1
