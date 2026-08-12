#!/usr/bin/env bash
# Study Loop UI start — Web UI サーバーを起動する。
#
# 動作:
#   1. bootstrap.sh を呼んで venv / 依存を idempotent に整える
#   2. PID ファイルから既起動の有無を確認
#   3. ポート 8765 から空きを探して起動（最大 8775）
#   4. PID とポートを記録、ログを stdout に流す
#
# 引数:
#   --root <path>   Study Loop セッションのルート（デフォルト: $PWD/.study）
#   --port <n>      固定ポート（指定時は衝突しても自動シフトしない）
#   --host <addr>   bind するアドレス（デフォルト: 127.0.0.1）
#   --backend <mode> Codex 連携の既定（auto/codex/manual、デフォルト: auto）
#   --no-open       起動後にブラウザを自動で開かない（デフォルト: 開く）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
PID_FILE="$SCRIPT_DIR/.study-server.pid"
META_FILE="$SCRIPT_DIR/.study-server.meta"
LOG_FILE="$SCRIPT_DIR/.study-server.log"
SERVER_PY="$SCRIPT_DIR/server.py"

# Defaults
ROOT="$PWD/.study"
PORT=""
HOST="127.0.0.1"
BACKEND="auto"
OPEN_BROWSER=1
DEFAULT_PORT_BASE=8765
PORT_RANGE=10

# 引数パース
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --backend) BACKEND="$2"; shift 2;;
    --no-open) OPEN_BROWSER=0; shift 1;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

case "$HOST" in
  127.0.0.1|localhost|::1) ;;
  *) echo "ERROR: --host は loopback アドレスだけを指定できます" >&2; exit 2;;
esac

case "$BACKEND" in
  auto|codex|manual) ;;
  *) echo "ERROR: --backend は auto, codex, manual のいずれかです" >&2; exit 2;;
esac

# ブラウザを OS 標準コマンドで開く。失敗してもスクリプト全体を落とさない
# （呼び出し側で if の条件式として使うことで set -e の対象外にする）。
# Claude Code の sandbox 等で open がブロックされる環境でも、標準エラーを
# 抑制した上で戻り値を返すだけに留める。
open_browser() {
  local url="$1"
  case "$(uname -s)" in
    Darwin)
      open "$url" >/dev/null 2>&1
      ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1
      else
        return 1
      fi
      ;;
    *)
      return 1
      ;;
  esac
}

# .study-server.meta の "host=... port=... ..." から URL を組み立てる。
# パースできなければ空文字を返す。
meta_to_url() {
  local meta="$1" h p
  h="$(sed -nE 's/.*host=([^ ]+).*/\1/p' <<<"$meta")"
  p="$(sed -nE 's/.*port=([^ ]+).*/\1/p' <<<"$meta")"
  if [[ -n "$h" && -n "$p" ]]; then
    echo "http://$h:$p"
  fi
}

# URL を案内する。OPEN_BROWSER=1 ならブラウザで開いてから案内文言を出し、
# 開けなかった／--no-open のときは従来どおり URL 表示だけにする。
announce_and_open() {
  local url="$1"
  if [[ "$OPEN_BROWSER" -eq 1 ]] && open_browser "$url"; then
    echo "  ✓ ブラウザで開きました: $url"
  else
    echo "  Open: $url"
  fi
}

# 既起動チェック。kill -0 の挙動は3通り:
#   exit 0                            → プロセス存在 (alive)
#   exit 1 + "no such process"        → プロセス不存在 (dead)
#   exit 1 + "not permitted"          → サンドボックス制限で確認不能 (unknown)
# unknown のときは PID ファイルを保持する（誤って消すと別シェルで動いてるサーバーが孤児になる）。
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]]; then
    KILL_RC=0
    KILL_ERR="$(kill -0 "$OLD_PID" 2>&1)" || KILL_RC=$?
    if [[ $KILL_RC -eq 0 ]]; then
      OLD_META="$(cat "$META_FILE" 2>/dev/null || echo 'unknown')"
      echo "✓ Study Loop UI is already running (PID $OLD_PID) — $OLD_META"
      OLD_URL="$(meta_to_url "$OLD_META")"
      if [[ -n "$OLD_URL" ]]; then
        announce_and_open "$OLD_URL"
      fi
      exit 0
    elif [[ "$KILL_ERR" == *"not permitted"* ]]; then
      OLD_META="$(cat "$META_FILE" 2>/dev/null || echo 'unknown')"
      echo "⚠ Cannot verify PID $OLD_PID due to sandbox restriction. Assuming alive — $OLD_META" >&2
      echo "  If a fresh start is needed, run 'bash $SCRIPT_DIR/stop.sh' from an unsandboxed shell first." >&2
      OLD_URL="$(meta_to_url "$OLD_META")"
      if [[ -n "$OLD_URL" ]]; then
        announce_and_open "$OLD_URL"
      fi
      exit 0
    else
      # 本当に死んでいる → 掃除
      rm -f "$PID_FILE" "$META_FILE"
    fi
  else
    rm -f "$PID_FILE" "$META_FILE"
  fi
fi

# bootstrap (venv + deps)
bash "$SCRIPT_DIR/bootstrap.sh"

# .study ディレクトリの存在チェック（warn だけ、サーバーは起動する）
if [[ ! -d "$ROOT" ]]; then
  echo "⚠ $ROOT が存在しません。Claude Code でセッション開始後にリロードしてください。" >&2
fi

# サーバー起動。bind の事前プローブはしない（codex CLI のように sandbox-exec で
# ソケット bind が制限される環境では、全ポートが誤って「使用中」と判定されるため）。
# 代わりに実際に起動を試みて、ポート衝突なら Flask 側のエラーで検知して次へ進む。
NEW_PID=""
start_server() {
  local port=$1
  : > "$LOG_FILE"
  nohup "$VENV_PYTHON" "$SERVER_PY" --host "$HOST" --port "$port" --root "$ROOT" --backend "$BACKEND" \
    > "$LOG_FILE" 2>&1 &
  local pid=$!

  local _
  for _ in 1 2 3 4 5 6; do
    sleep 0.5
    if grep -q "Running on" "$LOG_FILE" 2>/dev/null; then
      NEW_PID=$pid
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
  done
  # 3秒経って生存していて "Running on" 未検出 → ログ遅延と見なして成功扱い
  NEW_PID=$pid
  return 0
}

is_port_in_use_error() {
  grep -qE "Address already in use|Errno (48|98)" "$LOG_FILE" 2>/dev/null
}

is_sandbox_bind_error() {
  # macOS sandbox-exec が socket bind を蹴ると Python は OSError: [Errno 1] Operation not permitted を吐く
  grep -qE "Operation not permitted|PermissionError" "$LOG_FILE" 2>/dev/null
}

abort_sandbox() {
  echo "ERROR: socket bind was rejected by the sandbox. Run from an unsandboxed shell or" >&2
  echo "       elevate permissions (e.g. codex CLI with approval). Last log:" >&2
  tail -n 20 "$LOG_FILE" >&2
  exit 1
}

if [[ -n "$PORT" ]]; then
  echo "→ Starting Study Loop UI on http://$HOST:$PORT  (root: $ROOT)"
  if ! start_server "$PORT"; then
    if is_sandbox_bind_error; then abort_sandbox; fi
    echo "ERROR: failed to start on port $PORT. Last log:" >&2
    tail -n 20 "$LOG_FILE" >&2
    exit 1
  fi
else
  for ((p=DEFAULT_PORT_BASE; p<DEFAULT_PORT_BASE+PORT_RANGE; p++)); do
    echo "→ Starting Study Loop UI on http://$HOST:$p  (root: $ROOT)"
    if start_server "$p"; then
      PORT=$p
      break
    fi
    if is_sandbox_bind_error; then abort_sandbox; fi
    if ! is_port_in_use_error; then
      echo "ERROR: server crashed for non-port reason on $p. Last log:" >&2
      tail -n 20 "$LOG_FILE" >&2
      exit 1
    fi
    echo "  port $p busy, trying next..."
  done
  if [[ -z "$PORT" ]]; then
    echo "ERROR: no available port in $DEFAULT_PORT_BASE-$((DEFAULT_PORT_BASE+PORT_RANGE-1))" >&2
    exit 1
  fi
fi

echo "$NEW_PID" > "$PID_FILE"
echo "host=$HOST port=$PORT root=$ROOT backend=$BACKEND" > "$META_FILE"

echo "✓ Study Loop UI started (PID $NEW_PID)"
announce_and_open "http://$HOST:$PORT"
echo "  Stop: bash $SCRIPT_DIR/stop.sh  (or via /study-ui-stop)"
