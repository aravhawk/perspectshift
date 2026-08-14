# PerceptShift operational console

React + TypeScript + Vite console for local PerceptShift operations.

## Develop

```bash
pnpm install
pnpm dev
```

Proxies `/api` to `http://127.0.0.1:8741`.

## Build / test

```bash
pnpm build
pnpm test
pnpm test:e2e
```

Production source maps are disabled by default (`build.sourcemap: false`).
