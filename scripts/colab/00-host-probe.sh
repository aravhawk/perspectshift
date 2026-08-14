#!/usr/bin/env bash
# Colab host probe — record execution context truthfully.
set -euo pipefail

LOG_DIR="${PS_CI_LOGS:-/content/ps-ci/logs}"
mkdir -p "$LOG_DIR"
OUT="$LOG_DIR/colab_host_probe.log"

{
  echo "=== colab_host_probe $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  uname -a
  uname -m
  getconf LONG_BIT || true
  cat /etc/os-release
  python3 --version || true
  nproc
  free -h || true
  df -h /content || true
  id
  lscpu || true
  command -v docker || true
  command -v podman || true
  command -v buildah || true
  command -v qemu-aarch64-static || true
  command -v debootstrap || true
  command -v proot || true
} 2>&1 | tee "$OUT"

echo "Wrote $OUT"
