---
allowed-tools: Bash(bash:*)
description: Study Loop Web UI サーバーを停止する
disable-model-invocation: false
---

`/study-ui-stop` は `/study-ui` で起動中の Web UI サーバーを停止します。

## 動作手順

1. `${CLAUDE_PLUGIN_ROOT}/skills/study-loop/scripts/stop.sh` を Bash で実行する:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/study-loop/scripts/stop.sh"
```

2. stop.sh は以下を行う:
   - PID ファイルを読み、`kill -TERM` でグレースフル停止
   - 3秒待っても止まらなければ `kill -KILL`
   - PID ファイルと meta ファイルを削除

3. 出力をユーザーに伝える。

## 注意

- サーバーが起動していない場合は安全に終了する（`✓ No running Study Loop UI server`）
- PID ファイルが残っているがプロセスが既に死んでいる場合は、自動で掃除する
- 強制停止が走った場合（`Force-stopped`）は、なんらかの応答無し状態だった可能性をユーザーに伝える
