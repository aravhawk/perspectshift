# Installation

## Prerequisites

- Ubuntu 24.04 recommended for production installs.
- CMake ≥ 3.22, Ninja, a C++20 compiler.
- Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 24 with Corepack/pnpm for the console.
- Optional: ROS 2 Jazzy for `perceptshift_ros` / bringup.
- User-supplied ONNX models and datasets (none are bundled).

## Bootstrap (Ubuntu)

```bash
./scripts/bootstrap-ubuntu.sh --with-ros
```

Use `--dry-run` to print actions. Use `--noninteractive` in CI.

## Build from source

```bash
make setup
make build
make test
```

## Debian packages

The canonical release package requires ROS 2 Jazzy and ONNX Runtime libraries:

```bash
make package
./scripts/install-local.sh --from-packages dist/
perceptshift version
perceptshift doctor --json
./scripts/uninstall-local.sh
```

`make package` fails closed if the complete supported environment is missing.
`make package-core-dev` produces an explicitly named non-release C++ core artifact.

## Containers

Individual images under `deploy/containers/` are not an integrated product stack.
A compose file is not shipped. Build a specific image when you need that tool:

```bash
docker build -f deploy/containers/Dockerfile.runtime -t perceptshift-runtime:local .
docker build -f deploy/containers/Dockerfile.api -t perceptshift-api:local .
docker build -f deploy/containers/Dockerfile.console -t perceptshift-console:local .
```

- Runtime image: pass `--bundle` and the intended command; default is one-shot `--doctor`.
- API image: artifact-store mode only (no ROS).
- Console image: static UI; configure the API base URL in the console. Same-origin `/api` is not proxied.

## Systemd

Unit templates live under `deploy/systemd/`. Services run as non-root users with hardening options. They do not start without required configuration (see packaging postinst).
