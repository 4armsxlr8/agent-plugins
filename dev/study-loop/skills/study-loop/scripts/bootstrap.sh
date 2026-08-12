#!/usr/bin/env bash
# Study Loop UI bootstrap — venv 作成と依存インストールを idempotent に行う。
# start.sh から自動で呼ばれるので、ユーザーが直接実行する必要はない。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
PYTHON_BIN="${STUDY_LOOP_PYTHON:-python3}"

if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "ERROR: requirements.txt not found at $REQUIREMENTS" >&2
  exit 1
fi

# venv の作成
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "→ Creating venv at $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# 依存の確認 — flask が無ければインストール
if ! "$VENV_DIR/bin/python" -c "import flask, markdown, pymdownx" 2>/dev/null; then
  echo "→ Installing dependencies (flask / markdown / pymdown-extensions) ..."
  "$VENV_DIR/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
  "$VENV_DIR/bin/pip" install -q -r "$REQUIREMENTS"
  echo "✓ Dependencies installed"
else
  echo "✓ Dependencies already satisfied"
fi
