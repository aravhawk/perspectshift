#!/usr/bin/env bash
# Record a single verification tier evidence file.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${1:?tier name}"
CLASS="${2:?required|external}"
STATUS="${3:?status}"
COMMAND="${4:?command}"
EXIT_CODE="${5:?exit}"
START="${6:?start}"
END="${7:?end}"
DURATION="${8:?duration}"
LOG_PATH="${9:-}"
REASON="${10:-}"

OUT="$ROOT/build/verification/tiers"
mkdir -p "$OUT" "$ROOT/build/verification/logs"
FP="$("$ROOT/scripts/source-fingerprint.sh")"
HOST_OS="$(uname -s)"; HOST_ARCH="$(uname -m)"
LOG_SHA=""
if [[ -n "$LOG_PATH" && -f "$LOG_PATH" ]]; then
  if command -v sha256sum >/dev/null; then LOG_SHA=$(sha256sum "$LOG_PATH" | awk '{print $1}')
  else LOG_SHA=$(shasum -a 256 "$LOG_PATH" | awk '{print $1}'); fi
fi
python3 - <<PY
import json
doc = {
  "tier": "$NAME",
  "classification": "$CLASS",
  "status": "$STATUS",
  "command": """$COMMAND""",
  "exit_code": int("$EXIT_CODE"),
  "start": "$START",
  "end": "$END",
  "duration_seconds": float("$DURATION"),
  "host": {"os": "$HOST_OS", "arch": "$HOST_ARCH", "context": "record-tier"},
  "source_fingerprint": "$FP",
  "log_path": "$LOG_PATH" or None,
  "log_sha256": "$LOG_SHA" or None,
  "artifact_paths": [],
  "reason": """$REASON""" or None,
}
open("$OUT/$NAME.json","w",encoding="utf-8").write(json.dumps(doc, indent=2)+"\n")
print("$NAME=$STATUS fp=$FP")
PY
