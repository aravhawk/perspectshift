#!/usr/bin/env bash
# Uninstall locally installed PerceptShift packages or prefix files.
set -euo pipefail

PURGE=0
PREFIX="${PREFIX:-/usr/local}"

usage() {
  cat <<'EOF'
Usage: uninstall-local.sh [--prefix DIR] [--purge]

  --prefix DIR   Prefix used by install-local.sh (default: /usr/local)
  --purge        Also remove managed state under /var/lib/perceptshift
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift ;;
    --purge) PURGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if command -v dpkg >/dev/null 2>&1; then
  PKGS=$(dpkg -l 'perceptshift*' 2>/dev/null | awk '/^ii/{print $2}' || true)
  if [[ -n "$PKGS" ]]; then
    if [[ "$PURGE" -eq 1 ]]; then
      # shellcheck disable=SC2086
      sudo apt-get purge -y $PKGS || sudo dpkg --purge $PKGS
    else
      # shellcheck disable=SC2086
      sudo apt-get remove -y $PKGS || sudo dpkg --remove $PKGS
    fi
  fi
fi

for bin in perceptshift perceptshift-runtime perceptshift-bench-worker perceptshift-inspect-worker; do
  if [[ -x "$PREFIX/bin/$bin" ]]; then
    sudo rm -f "$PREFIX/bin/$bin"
  fi
done

if [[ -d "$PREFIX/lib/libperceptshift_core.so" || -f "$PREFIX/lib/libperceptshift_core.so" ]]; then
  sudo rm -f "$PREFIX/lib/libperceptshift_core.so"*
fi

if [[ "$PURGE" -eq 1 ]]; then
  sudo rm -rf /var/lib/perceptshift /var/log/perceptshift
  echo "Purged managed state under /var/lib/perceptshift and /var/log/perceptshift"
else
  echo "Preserved user data under /var/lib/perceptshift (use --purge to remove)"
fi

echo "uninstall-local.sh complete"
