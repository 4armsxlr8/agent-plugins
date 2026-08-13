#!/usr/bin/env bash
# Study Loop UI stop — 起動中のサーバーを停止する。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.study-server.pid"
META_FILE="$SCRIPT_DIR/.study-server.meta"

if [[ ! -f "$PID_FILE" ]]; then
  echo "✓ No running Study Loop UI server (PID file not found)"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  echo "⚠ PID file exists but is empty. Cleaning up."
  rm -f "$PID_FILE" "$META_FILE"
  exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
  echo "✓ Process $PID already stopped. Cleaning up stale PID file."
  rm -f "$PID_FILE" "$META_FILE"
  exit 0
fi

META="$(cat "$META_FILE" 2>/dev/null || echo 'unknown')"
echo "→ Stopping Study Loop UI (PID $PID, $META) ..."
kill -TERM "$PID" 2>/dev/null || true

# 終了待ち (最大 3秒)
for _ in 1 2 3 4 5 6; do
  sleep 0.5
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE" "$META_FILE"
    echo "✓ Stopped"
    exit 0
  fi
done

# 終わらなければ強制
echo "⚠ TERM signal didn't stop the process, sending KILL"
kill -KILL "$PID" 2>/dev/null || true
sleep 0.5
rm -f "$PID_FILE" "$META_FILE"
echo "✓ Force-stopped"
