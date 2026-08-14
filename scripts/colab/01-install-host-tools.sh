#!/usr/bin/env bash
# Bootstrap Colab host tools for Noble amd64/arm64 userlands.
set -euo pipefail

LOG_DIR="${PS_CI_LOGS:-/content/ps-ci/logs}"
mkdir -p "$LOG_DIR" /content/ps-ci/artifacts
LOG="$LOG_DIR/01-host-tools.log"

run() {
  echo "+ $*" | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

export DEBIAN_FRONTEND=noninteractive

if command -v apt-get >/dev/null 2>&1; then
  run sudo apt-get update -y
  run sudo apt-get install -y --no-install-recommends \
    git curl wget ca-certificates gnupg jq rsync zip unzip tar xz-utils zstd \
    build-essential cmake ninja-build clang lld pkg-config \
    python3 python3-pip python3-venv python3-dev \
    debootstrap qemu-user-static binfmt-support \
    file binutils \
    || true
  # proot is optional but preferred for chroot-less rootfs
  run sudo apt-get install -y --no-install-recommends proot || echo "proot unavailable" | tee -a "$LOG"
fi

# Verify qemu-aarch64-static exists after install
if [[ -x /usr/bin/qemu-aarch64-static ]]; then
  echo "qemu-aarch64-static present" | tee -a "$LOG"
  file /usr/bin/qemu-aarch64-static | tee -a "$LOG"
else
  echo "WARN: qemu-aarch64-static missing after apt" | tee -a "$LOG"
fi

echo "Host tools bootstrap finished" | tee -a "$LOG"
