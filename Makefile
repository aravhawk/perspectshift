# PerceptShift root Makefile — prints exact subcommands and fails fast.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ARCH := $(shell uname -m)
ifeq ($(filter $(ARCH),aarch64 arm64),$(ARCH))
  HOST_PRESET := dev-arm64
  RELEASE_PRESET := release-arm64
else
  HOST_PRESET := dev-x64
  RELEASE_PRESET := release-x64
endif

.PHONY: help setup bootstrap configure build build-release build-debug build-arm64 \
	format fmt format-check lint typecheck unit integration ros-test web-test \
	test e2e security-test fuzz-smoke coverage verify verify-host verify-arm verify-ros \
	verify-clean-room package package-core-dev container-test install-local uninstall-local sbom \
	docs docs-check clean

help:
	@printf '%s\n' \
	  'PerceptShift make targets:' \
	  '  setup / bootstrap   Install local tooling hooks' \
	  '  build               Configure and build (current arch preset)' \
	  '  test                Unit + integration subset' \
	  '  verify              Canonical complete software release verifier (26 required tiers)' \
	  '  verify-host         Fast host-only software subset' \
	  '  verify-arm          Native AArch64 gate' \
	  '  package             Build the complete supported Debian release package' \
	  '  package-core-dev    Explicit non-release CPack core developer artifact' \
	  '  docs / docs-check   Documentation targets' \
	  '  fmt / lint          Format and lint'

setup bootstrap:
	@echo '+ ./scripts/bootstrap-ubuntu.sh (may SKIP on non-Ubuntu)'
	@if [[ "$$(uname -s)" == "Linux" ]] && [[ -f /etc/os-release ]] && grep -qi ubuntu /etc/os-release; then \
	  ./scripts/bootstrap-ubuntu.sh; \
	else \
	  echo "SKIP bootstrap-ubuntu.sh on $$(uname -s); install deps manually"; \
	fi
	@if command -v pre-commit >/dev/null; then pre-commit install; else echo "SKIP pre-commit install (not installed)"; fi

configure:
	@echo "+ cmake --preset $(HOST_PRESET)"
	cmake --preset $(HOST_PRESET)

build: configure
	@echo "+ cmake --build --preset $(HOST_PRESET)"
	cmake --build --preset $(HOST_PRESET) -j

build-release:
	@echo "+ cmake --preset $(RELEASE_PRESET)"
	cmake --preset $(RELEASE_PRESET)
	cmake --build --preset $(RELEASE_PRESET) -j

build-debug:
	cmake --preset debug
	cmake --build --preset debug -j

build-arm64:
	@echo '+ build-arm64 requires AArch64 host'
	@uname -m | grep -E 'aarch64|arm64'
	cmake --preset release-arm64
	cmake --build --preset release-arm64 -j

fmt format:
	@echo '+ clang-format / ruff / prettier'
	@command -v clang-format >/dev/null
	find cpp ros2_ws -name '*.cpp' -o -name '*.hpp' | xargs clang-format -i
	@command -v ruff >/dev/null
	ruff format python
	@command -v pnpm >/dev/null
	(cd web && pnpm exec prettier -w .)

format-check:
	@command -v clang-format >/dev/null
	find cpp ros2_ws \( -name '*.cpp' -o -name '*.hpp' \) -print0 | xargs -0 clang-format --dry-run -Werror
	@command -v uv >/dev/null
	uv run ruff format --check python

lint:
	@command -v uv >/dev/null
	uv run ruff check python
	@command -v pnpm >/dev/null
	(cd web && pnpm lint)

typecheck:
	@command -v uv >/dev/null
	uv sync --group dev >/dev/null
	uv run pyright
	@command -v pnpm >/dev/null
	(cd web && pnpm exec tsc -p tsconfig.json --noEmit)

unit:
	ctest --test-dir $(ROOT)/build/$(HOST_PRESET) --output-on-failure
	@command -v uv >/dev/null
	uv run pytest python -q -m 'not integration'

integration:
	@command -v uv >/dev/null
	uv run pytest tests -q

ros-test:
	@if command -v ros2 >/dev/null; then \
	  echo '+ colcon test'; \
	  bash -lc 'source /opt/ros/jazzy/setup.bash; cd ros2_ws && colcon test --event-handlers console_direct+ && colcon test-result --verbose'; \
	else \
	  echo 'ROS not installed; ros-test incomplete' >&2; \
	  exit 1; \
	fi

web-test:
	@command -v pnpm >/dev/null
	(cd web && pnpm test)

test: unit integration

e2e:
	./scripts/run-e2e.sh

security-test:
	@command -v uv >/dev/null
	uv run pytest tests/security -q

fuzz-smoke:
	./scripts/run-fuzz.sh

coverage:
	cmake --preset coverage
	cmake --build --preset coverage -j
	ctest --test-dir build/coverage --output-on-failure

verify:
	./scripts/release-verify.sh

verify-host:
	./scripts/verify-all.sh --tier host_software

verify-arm:
	./scripts/run-arm-acceptance.sh

verify-ros:
	./scripts/verify-all.sh --tier ros_jazzy

verify-clean-room:
	./scripts/clean-room-verify.sh

package:
	./scripts/package-deb.sh

package-core-dev:
	./scripts/package-core-dev.sh

container-test:
	./scripts/verify-all.sh --tier container_runtime

install-local:
	./scripts/install-local.sh

uninstall-local:
	./scripts/uninstall-local.sh

sbom:
	./scripts/generate-sbom.sh

docs:
	@echo 'Docs live under docs/; open docs/index.md'
	@ls docs/*.md | wc -l

docs-check:
	python3 -c 'from pathlib import Path; required=["docs/index.md","docs/architecture.md","docs/quickstart.md","docs/limitations.md","docs/threat-model.md","docs/security.md","docs/privacy.md","docs/ros2-integration.md","docs/benchmarking-methodology.md","docs/runtime-policy.md","docs/model-adapters.md"]; missing=[p for p in required if not Path(p).exists()]; assert not missing, missing; print("docs-check ok")'

clean:
	rm -rf build build-debug build-asan build-tsan dist .cache/onnxruntime-build
	rm -rf ros2_ws/build ros2_ws/install ros2_ws/log
