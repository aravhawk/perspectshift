#!/usr/bin/env bash
# Debian package build + full installed-product acceptance on Ubuntu 24.04 arm64.
# Proves CLI, API, ROS packages/runtime, systemd accounts/dirs, and purge.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
OUT_DIR="${DIST_DIR:-$ROOT/dist}"
EVIDENCE_DIR="${PERCEPTSHIFT_PACKAGE_EVIDENCE:-$ROOT/build/verification/artifacts/packaging}"
mkdir -p "$OUT_DIR" "$EVIDENCE_DIR"

echo "Proving arm64..."
arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m)"
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64, got $arch" >&2; exit 1; }

ORT_LINUX="$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0"
if [[ ! -d "$ORT_LINUX" ]]; then
  echo "Missing $ORT_LINUX" >&2
  exit 1
fi

BUILDER="ps-deb-builder-$$"
INSTALLER="ps-deb-install-$$"
cleanup() {
  docker rm -f "$BUILDER" "$INSTALLER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Phase 1: build release .deb inside ROS Jazzy arm64"
docker run -d --name "$BUILDER" --platform "$PLATFORM" \
  -v "$ROOT:/src:ro" \
  -v "$OUT_DIR:/dist" \
  -v "$ROOT/.cache:/cache:ro" \
  ros:jazzy-ros-base sleep infinity >/dev/null

docker exec "$BUILDER" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
apt-get update -qq
apt-get install -y -qq build-essential cmake ninja-build git python3 python3-pip python3-venv \
  python3-colcon-common-extensions python3-setuptools dpkg-dev file binutils rsync nlohmann-json3-dev \
  ros-jazzy-rclcpp-lifecycle ros-jazzy-rclcpp-components ros-jazzy-sensor-msgs \
  ros-jazzy-diagnostic-updater ros-jazzy-launch-ros ros-jazzy-lifecycle-msgs \
  ros-jazzy-rclpy ros-jazzy-image-transport ros-jazzy-cv-bridge \
  libssl-dev zlib1g-dev ca-certificates curl pkg-config >/dev/null
# Writable work tree (source is read-only).
rm -rf /work
mkdir -p /work
rsync -a --exclude build --exclude .venv --exclude .cache --exclude node_modules \
  --exclude dist --exclude "**/__pycache__" --exclude .git --exclude ros2_ws/build \
  --exclude ros2_ws/install --exclude ros2_ws/log \
  /src/ /work/
mkdir -p /work/.cache
cp -a /cache/onnxruntime-linux-aarch64-1.28.0 /work/.cache/
cd /work
export PERCEPTSHIFT_ORT_ROOT=/work/.cache/onnxruntime-linux-aarch64-1.28.0
export DIST_DIR=/dist
export PERCEPTSHIFT_DEB_BUILD=/work/build/deb-release
chmod +x scripts/build-release-deb.sh scripts/package-deb.sh
./scripts/package-deb.sh
'

DEB="$(ls -1t "$OUT_DIR"/perceptshift_*.deb 2>/dev/null | head -1 || true)"
[[ -n "$DEB" && -s "$DEB" ]] || { echo "no deb produced in $OUT_DIR" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
  DEB_SHA="$(sha256sum "$DEB" | awk '{print $1}')"
else
  DEB_SHA="$(shasum -a 256 "$DEB" | awk '{print $1}')"
fi
DEB_BASE="$(basename "$DEB")"
echo "Built $DEB_BASE sha256=$DEB_SHA"
cp -v "$DEB" "$EVIDENCE_DIR/"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb -I "$DEB" | tee "$EVIDENCE_DIR/dpkg-deb-I.txt"
else
  docker run --rm --platform "$PLATFORM" -v "$DEB:/pkg.deb:ro" ubuntu:24.04 \
    bash -lc 'apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dpkg >/dev/null && dpkg-deb -I /pkg.deb' \
    | tee "$EVIDENCE_DIR/dpkg-deb-I.txt"
fi
echo "$DEB_SHA  $DEB_BASE" | tee "$EVIDENCE_DIR/deb.sha256"

echo "==> Phase 2: fresh install environment (ROS Jazzy prerequisite only)"
docker run -d --name "$INSTALLER" --platform "$PLATFORM" \
  -v "$OUT_DIR:/dist:ro" \
  -v "$ROOT/tests:/tests:ro" \
  -v "$EVIDENCE_DIR:/evidence" \
  ros:jazzy-ros-base sleep infinity >/dev/null

docker exec -e DEB_BASE="$DEB_BASE" -e DEB_SHA="$DEB_SHA" "$INSTALLER" \
  bash /tests/package/installed-service-e2e.sh

echo "STATUS=PASS gate=debian_arm64_package_install_uninstall deb=$DEB_BASE sha256=$DEB_SHA"
