# Operator workflow

1. **Prepare host** — install dependencies; run `perceptshift doctor`.
2. **Validate inputs** — inspect the ONNX model; validate dataset manifests.
3. **Forge** — run offline orchestration on the target class of hardware you will deploy.
4. **Certify** — review quality and latency gates; keep only certified profiles.
5. **Bundle** — verify integrity; optionally sign with Ed25519.
6. **Deploy** — mount/install the bundle; launch ROS or standalone runtime.
7. **Operate** — monitor health, traces, switches; use pin/policy services only when mutation services are enabled.
8. **Recover** — use `RequestRecovery` when prerequisites are met; otherwise remain fail-closed.

Never treat offline-attested quality floors as guaranteed runtime accuracy under distribution shift.
