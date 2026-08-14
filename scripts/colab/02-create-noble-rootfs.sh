#!/usr/bin/env bash
# Create Ubuntu 24.04 Noble amd64 and arm64 rootfs under /content/ps-ci.
set -euo pipefail

PS_CI="${PS_CI:-/content/ps-ci}"
LOG_DIR="${PS_CI}/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/02-noble-rootfs.log"

AMD64_ROOT="${PS_CI}/noble-amd64"
ARM64_ROOT="${PS_CI}/noble-arm64"

log() { echo "$*" | tee -a "$LOG"; }

ARCH="$(uname -m)"
log "Host arch: $ARCH"
log "Creating Noble rootfs contexts..."

if [[ ! -d "$AMD64_ROOT/usr" ]]; then
  log "debootstrap amd64 noble -> $AMD64_ROOT"
  sudo debootstrap --arch=amd64 noble "$AMD64_ROOT" http://archive.ubuntu.com/ubuntu/ 2>&1 | tee -a "$LOG"
else
  log "amd64 rootfs already present"
fi

if [[ ! -d "$ARM64_ROOT/usr" ]]; then
  log "debootstrap arm64 noble (foreign) -> $ARM64_ROOT"
  sudo debootstrap --arch=arm64 --foreign noble "$ARM64_ROOT" http://ports.ubuntu.com/ubuntu-ports 2>&1 | tee -a "$LOG"
  if [[ -x /usr/bin/qemu-aarch64-static ]]; then
    sudo cp /usr/bin/qemu-aarch64-static "$ARM64_ROOT/usr/bin/"
  fi
  # Second stage
  if command -v proot >/dev/null 2>&1 && [[ -x "$ARM64_ROOT/usr/bin/qemu-aarch64-static" || -x /usr/bin/qemu-aarch64-static ]]; then
    QEMU="${ARM64_ROOT}/usr/bin/qemu-aarch64-static"
    [[ -x "$QEMU" ]] || QEMU=/usr/bin/qemu-aarch64-static
    log "Completing arm64 second-stage via proot+qemu"
    sudo proot -q "$QEMU" -S "$ARM64_ROOT" /debootstrap/debootstrap --second-stage 2>&1 | tee -a "$LOG"
  elif [[ -d /proc/sys/fs/binfmt_misc ]] && command -v chroot >/dev/null 2>&1; then
    log "Completing arm64 second-stage via chroot"
    sudo chroot "$ARM64_ROOT" /debootstrap/debootstrap --second-stage 2>&1 | tee -a "$LOG"
  else
    log "ERROR: cannot complete arm64 second-stage (no proot/chroot path)"
    exit 1
  fi
else
  log "arm64 rootfs already present"
fi

# Prove arm64 execution
prove_arm64() {
  local root="$1"
  if command -v proot >/dev/null 2>&1; then
    sudo proot -q /usr/bin/qemu-aarch64-static -S "$root" /usr/bin/uname -m 2>&1 | tee -a "$LOG"
  else
    sudo chroot "$root" /usr/bin/uname -m 2>&1 | tee -a "$LOG"
  fi
}

log "Proving arm64 userland..."
ARM_UNAME="$(prove_arm64 "$ARM64_ROOT" | tail -n1)"
log "arm64 uname -m => $ARM_UNAME"
if [[ "$ARM_UNAME" != "aarch64" ]]; then
  log "ERROR: expected aarch64 inside arm64 rootfs, got: $ARM_UNAME"
  exit 1
fi

# Write context manifests
python3 - <<'PY' | tee -a "$LOG"
import json, os, platform, time
from pathlib import Path
ps = Path(os.environ.get("PS_CI", "/content/ps-ci"))
manifest = {
  "schema_version": "execution-context-v1",
  "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "colab_host": {"uname_m": platform.machine(), "system": platform.system(), "release": platform.release()},
  "noble_amd64_root": str(ps / "noble-amd64"),
  "noble_arm64_root": str(ps / "noble-arm64"),
  "arm64_execution": "qemu-user" if platform.machine() in ("x86_64", "amd64") else "native",
  "claim_scope": "software_correctness_only",
  "performance_claims_allowed": False,
}
(ps / "artifacts" / "execution-contexts.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
PY

log "Noble rootfs bootstrap OK"
