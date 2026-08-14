#!/usr/bin/env bash
# Build a functional monolithic PerceptShift Debian package for Ubuntu 24.04 arm64.
# Includes: native runtime, managed Python site-packages, ROS overlay, systemd helpers.
# Does NOT rely on a source checkout, build-machine .venv, or preinstalled FastAPI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${DIST_DIR:-$ROOT/dist}"
VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION")"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
esac

ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-}"
if [[ -z "$ORT_ROOT" ]]; then
  for candidate in \
    "$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0" \
    "$ROOT/.cache/onnxruntime"; do
    if [[ -d "$candidate/lib" ]]; then
      ORT_ROOT="$candidate"
      break
    fi
  done
fi
[[ -n "$ORT_ROOT" && -d "$ORT_ROOT/lib" ]] || {
  echo "PERCEPTSHIFT_ORT_ROOT (or .cache ORT) required" >&2
  exit 1
}

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/ps-deb-stage.XXXXXX")"
BUILD_DIR="${PERCEPTSHIFT_DEB_BUILD:-$ROOT/build/deb-release}"
WHEELHOUSE="$STAGE/wheelhouse"
PKG_ROOT="$STAGE/root"
DEBIAN_DIR="$PKG_ROOT/DEBIAN"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$OUT_DIR" "$PKG_ROOT" "$WHEELHOUSE" "$DEBIAN_DIR"

echo "==> Building native core into staging prefix"
cmake -S "$ROOT" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DPERCEPTSHIFT_ORT_ROOT="$ORT_ROOT" \
  -DPERCEPTSHIFT_BUILD_TESTS=OFF
cmake --build "$BUILD_DIR" -j"${JOBS:-$(nproc 2>/dev/null || echo 2)}"
DESTDIR="$PKG_ROOT" cmake --install "$BUILD_DIR"

echo "==> Building managed Python site-packages (all transitive wheels)"
# Isolate from a sourced ROS PYTHONPATH so pip cannot see launch-ros/setuptools conflicts.
python3 -m venv "$STAGE/build-venv"
env -u PYTHONPATH -u PYTHONHOME \
  "$STAGE/build-venv/bin/pip" install -q --upgrade pip wheel build setuptools
env -u PYTHONPATH -u PYTHONHOME \
  "$STAGE/build-venv/bin/pip" wheel -q -w "$WHEELHOUSE" \
  "$ROOT/python/perceptshift_common" \
  "$ROOT/python/perceptshift_forge" \
  "$ROOT/python/perceptshift_cli" \
  "$ROOT/python/perceptshift_api"
env -u PYTHONPATH -u PYTHONHOME \
  "$STAGE/build-venv/bin/pip" install -q --upgrade --no-compile \
  --prefix="$PKG_ROOT/usr/lib/perceptshift/py" \
  --no-index --find-links="$WHEELHOUSE" \
  perceptshift-common perceptshift-forge perceptshift-cli perceptshift-api
# Expose managed site-packages to system python3 via .pth (supports `import perceptshift_api`).
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
mkdir -p "$PKG_ROOT/usr/lib/python3/dist-packages"
echo "/usr/lib/perceptshift/py/lib/python${PY_VER}/site-packages" \
  >"$PKG_ROOT/usr/lib/python3/dist-packages/perceptshift.pth"
# Keep a copy of wheels for audit/reinstall evidence inside the package.
mkdir -p "$PKG_ROOT/usr/share/perceptshift/wheels"
cp -a "$WHEELHOUSE"/. "$PKG_ROOT/usr/share/perceptshift/wheels/"

echo "==> Building ROS Jazzy overlay into /usr/share/perceptshift/ros"
if [[ ! -f /opt/ros/jazzy/setup.bash ]]; then
  echo "ROS 2 Jazzy required to package perceptshift_bringup/ros/msgs" >&2
  exit 1
fi
# Ensure nlohmann headers exist (system package or FetchContent from core build).
if [[ ! -f /usr/include/nlohmann/json.hpp ]]; then
  if [[ -f "$BUILD_DIR/_deps/nlohmann_json-src/include/nlohmann/json.hpp" ]]; then
    mkdir -p "$PKG_ROOT/usr/include"
    cp -a "$BUILD_DIR/_deps/nlohmann_json-src/include/nlohmann" "$PKG_ROOT/usr/include/"
  elif [[ -f "$BUILD_DIR/_deps/nlohmann_json-src/single_include/nlohmann/json.hpp" ]]; then
    mkdir -p "$PKG_ROOT/usr/include"
    cp -a "$BUILD_DIR/_deps/nlohmann_json-src/single_include/nlohmann" "$PKG_ROOT/usr/include/"
  else
    echo "nlohmann/json.hpp missing; install nlohmann-json3-dev or rebuild core" >&2
    exit 1
  fi
fi
# shellcheck disable=SC1091
# Build ROS overlay in a clean prefix chain (do not inherit developer/workspace
# overlays like /tmp/ps/ros2_ws/install into the packaged setup.bash).
set +u
# Reset overlay env then source only Jazzy.
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH || true
source /opt/ros/jazzy/setup.bash
set -u
export CMAKE_PREFIX_PATH="${PKG_ROOT}/usr${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"
export LD_LIBRARY_PATH="${PKG_ROOT}/usr/lib/perceptshift:${PKG_ROOT}/usr/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
ROS_WS="$STAGE/ros_ws"
mkdir -p "$ROS_WS/src"
cp -a "$ROOT/ros2_ws/src/perceptshift_msgs" "$ROS_WS/src/"
cp -a "$ROOT/ros2_ws/src/perceptshift_ros" "$ROS_WS/src/"
cp -a "$ROOT/ros2_ws/src/perceptshift_bringup" "$ROS_WS/src/"
# Point ROS package at staged install + this tree's FetchContent nlohmann.
export PERCEPTSHIFT_REPO_ROOT="$ROOT"
(
  cd "$ROS_WS"
  colcon build \
    --merge-install \
    --install-base "$PKG_ROOT/usr/share/perceptshift/ros" \
    --cmake-args \
      -DCMAKE_BUILD_TYPE=Release \
      "-DCMAKE_PREFIX_PATH=${PKG_ROOT}/usr;${CMAKE_PREFIX_PATH}" \
      "-DCMAKE_CXX_FLAGS=-I${PKG_ROOT}/usr/include -I${BUILD_DIR}/_deps/nlohmann_json-src/include -I${BUILD_DIR}/_deps/nlohmann_json-src/single_include"
)
# Ensure wrapper default path exists.
test -f "$PKG_ROOT/usr/share/perceptshift/ros/setup.bash"
# Sanitize packaged setup.bash so it never references build-machine overlays.
SETUP_BASH="$PKG_ROOT/usr/share/perceptshift/ros/setup.bash"
python3 - "$SETUP_BASH" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'COLCON_CURRENT_PREFIX="' in line and "/opt/ros/jazzy" not in line and "dirname" not in line and "BASH_SOURCE" not in line:
        # Drop build-machine overlay assignment + following source line.
        i += 1
        if i < len(lines) and "_colcon_prefix_chain_bash_source_script" in lines[i]:
            i += 1
        continue
    out.append(line)
    i += 1
path.write_text("".join(out), encoding="utf-8")
print(f"sanitized {path}")
PY
# Verify no ephemeral build paths remain.
if grep -E '/tmp/|/work/|/src/ros2_ws' "$SETUP_BASH"; then
  echo "packaged ROS setup.bash still references build paths" >&2
  exit 1
fi

echo "==> Writing Debian control + maintainer scripts"
INSTALLED_SIZE="$(du -sk "$PKG_ROOT" | awk '{print $1}')"
cat >"$DEBIAN_DIR/control" <<EOF
Package: perceptshift
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: PerceptShift Maintainers <maintainers@perceptshift.local>
Section: science
Priority: optional
Installed-Size: ${INSTALLED_SIZE}
Depends: libc6, libstdc++6, libssl3 | libssl1.1, python3 (>= 3.12), adduser, ros-jazzy-rclcpp, ros-jazzy-rclcpp-lifecycle, ros-jazzy-sensor-msgs, ros-jazzy-launch-ros, ros-jazzy-rclpy, ros-jazzy-lifecycle-msgs, ros-jazzy-diagnostic-updater, ros-jazzy-rmw-cyclonedds-cpp
Description: Deadline-aware adaptive ONNX inference for Arm64 ROS 2
 Monolithic v1 package: native runtime, managed Python CLI/API,
 ROS Jazzy packages, and systemd units. Does not bundle models or datasets.
 ROS 2 Jazzy is a prerequisite for the runtime service.
EOF

install -m 0755 "$ROOT/packaging/debian/perceptshift.postinst" "$DEBIAN_DIR/postinst"
install -m 0755 "$ROOT/packaging/debian/perceptshift.prerm" "$DEBIAN_DIR/prerm"
install -m 0755 "$ROOT/packaging/debian/perceptshift.postrm" "$DEBIAN_DIR/postrm"

# Ensure entrypoints and wrappers are executable.
chmod 0755 "$PKG_ROOT/usr/bin/perceptshift" "$PKG_ROOT/usr/bin/perceptshift-api" \
  "$PKG_ROOT/usr/lib/perceptshift/bin/perceptshift-ros-runtime" \
  "$PKG_ROOT/usr/lib/perceptshift/bin/perceptshift-api-service"

# Drop DEBIAN from size calc already done; build package.
DEB_NAME="perceptshift_${VERSION}_${ARCH}.deb"
DEB_PATH="$OUT_DIR/$DEB_NAME"
rm -f "$DEB_PATH"
dpkg-deb --root-owner-group --build "$PKG_ROOT" "$DEB_PATH"

echo "==> Package produced: $DEB_PATH"
dpkg-deb -I "$DEB_PATH"
sha256sum "$DEB_PATH" | tee "$OUT_DIR/${DEB_NAME}.sha256"
ls -la "$DEB_PATH"
