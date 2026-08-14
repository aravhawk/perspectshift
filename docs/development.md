# Development

```bash
./scripts/bootstrap-ubuntu.sh
make setup
make build
make test
make verify-host
make verify
```

Devcontainer: `.devcontainer/devcontainer.json` (Ubuntu 24.04, non-root).

Formatting: `.clang-format`, Ruff, Prettier via `.pre-commit-config.yaml`.

Architecture boundaries and agent rules: [AGENTS.md](../AGENTS.md).
