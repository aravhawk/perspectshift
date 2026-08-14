#!/usr/bin/env bash
# Bootstrap Ubuntu 24.04 development dependencies for PerceptShift.
set -euo pipefail

DRY_RUN=0
WITH_ROS=0
NONINTERACTIVE=0
ARCH="$(uname -m)"

usage() {
  cat <<'EOF'
Usage: bootstrap-ubuntu.sh [options]

Options:
  --dry-run           Print actions without installing
  --with-ros          Install ROS 2 Jazzy packages
  --noninteractive    Assume CI / noninteractive apt
  -h, --help          Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --with-ros) WITH_ROS=1 ;;
    --noninteractive) NONINTERACTIVE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: $*"
  else
    echo "+ $*"
    "$@"
  fi
}

echo "Architecture: $ARCH"
if [[ "$NONINTERACTIVE" -eq 1 ]]; then
  export DEBIAN_FRONTEND=noninteractive
fi

APT_PACKAGES=(
  build-essential
  cmake
  ninja-build
  git
  curl
  ca-certificates
  pkg-config
  python3
  python3-venv
  python3-pip
  python3-setuptools
  clang
  clang-tidy
  clang-format
  libssl-dev
  zlib1g-dev
  libopencv-dev
  jq
  ripgrep
)

if [[ "$WITH_ROS" -eq 1 ]]; then
  APT_PACKAGES+=(
    ros-jazzy-ros-base
    ros-jazzy-rclcpp
    ros-jazzy-rclcpp-lifecycle
    ros-jazzy-rclcpp-components
    ros-jazzy-sensor-msgs
    ros-jazzy-diagnostic-msgs
    ros-jazzy-diagnostic-updater
    ros-jazzy-launch-ros
    ros-jazzy-nav2-lifecycle-manager
    python3-colcon-common-extensions
  )
fi

if command -v apt-get >/dev/null 2>&1; then
  run sudo apt-get update
  run sudo apt-get install -y "${APT_PACKAGES[@]}"
else
  echo "apt-get not available; print required packages and continue"
  printf '  %s\n' "${APT_PACKAGES[@]}"
fi

if ! command -v uv >/dev/null 2>&1; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: install uv from https://astral.sh/uv/install.sh"
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi

if command -v corepack >/dev/null 2>&1; then
  run corepack enable
  run corepack prepare pnpm@9.15.0 --activate
else
  echo "corepack not found; install Node.js 24+ to enable pnpm via Corepack"
fi

echo
echo "Version checks:"
command -v cmake >/dev/null && cmake --version | head -n 1 || echo "cmake: missing"
command -v python3 >/dev/null && python3 --version || echo "python3: missing"
command -v uv >/dev/null && uv --version || echo "uv: missing (install may require shell reload)"
command -v node >/dev/null && node --version || echo "node: missing"
command -v pnpm >/dev/null && pnpm --version || echo "pnpm: missing"
if [[ "$WITH_ROS" -eq 1 ]]; then
  command -v ros2 >/dev/null && ros2 --version || echo "ros2: missing or not sourced"
fi

echo "bootstrap-ubuntu.sh complete"
