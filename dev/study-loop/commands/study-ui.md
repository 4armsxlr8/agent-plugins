---
allowed-tools: Bash(bash:*)
argument-hint: "[--port <n>] [--root <path>] [--backend auto|codex|manual] [--no-open]  (default: --root .study --backend auto, ブラウザ自動起動)"
description: Study Loop Web UI を loopback にローカル起動し、ブラウザを自動で開いて案内する（Codex / 手動モード対応、--no-open で抑止可）
disable-model-invocation: false
---

`/study-ui` は Study Loop の Web UI サーバーを起動し、`http://localhost:8765` をブラウザで自動的に開いて案内するためのコマンドです。

## 動作手順

1. `${CLAUDE_PLUGIN_ROOT}/skills/study-loop/scripts/start.sh` を Bash で実行する。`$ARGUMENTS` をそのまま渡す（ユーザーが `--port 9000` などを指定した場合に効くように）。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/study-loop/scripts/start.sh" $ARGUMENTS
```

2. start.sh は以下を idempotent に行う:
   - venv が無ければ `bootstrap.sh` を呼んで作成 + 依存インストール
   - 既起動チェック（PID ファイル）。既起動でも既存 URL に対してブラウザを開く
   - 8765 から空きポートを探して bind
   - nohup で `server.py` をバックグラウンド起動
   - PID ファイルとログファイルを `scripts/` 配下に保存
   - 起動成功で **ブラウザを自動で開き**、「✓ ブラウザで開きました: http://...」の案内を stdout に出す。`--no-open` を指定した場合、または sandbox 等でブラウザを開けなかった場合は、従来どおり「Open: http://...」の URL 案内だけを出す（この場合も終了コードは 0）
   - `--backend auto`（既定）は、画面で明示して Codex 操作を選ぶまで Codex を起動しない。`manual` は Markdown 保存と Claude Code の手動フローだけを使う

3. 出力をユーザーに伝える。特に **URL（http://127.0.0.1:&lt;port&gt;）** を必ず明示すること。ブラウザが自動で開かなかった場合（`--no-open` 指定時や sandbox 制限時）は、案内した URL を手動で開くようユーザーに伝える。

4. UI ではまず Mission、成功条件、制約、対象外、保持期間、目標レベル、時間予算を入力する。確認画面で Codex を選ぶと、ローカル App Server 経由で診断・カリキュラム・採点を実行する。Codex が未導入または認証できない場合は、保存して Claude Code で従来どおり続けられる。

5. `.study` ディレクトリが見つからなかった旨の警告（`⚠ <path> が存在しません`）が出ていた場合、UI の新規セッションフォームか Claude Code 側の `/study-loop <topic>` を使うよう案内する。

6. 終了方法として `/study-ui-stop` または `bash <path>/stop.sh` を案内する。

## 注意

- 初回は依存インストール（flask / markdown / pymdown-extensions）に 10〜30秒かかる
- 既に起動中なら start.sh はサーバーの再起動はせず既存 URL でブラウザを開くだけなので、何度叩いても安全（かつ叩けばブラウザが開く）
- ブラウザを自動で開きたくない場合は `--no-open` を付ける。sandbox 環境などブラウザを起動できない環境でも、start.sh は失敗せず URL 案内だけを出して正常終了する
- ユーザーが `--port` を明示した場合はその固定値を使う、なければ自動で空きポートを探す
- `--host` は安全のため `127.0.0.1`、`localhost`、`::1` 以外を受け付けない
- Codex の承認・追加質問は UI のジョブ画面で一回ごとに処理する。ブラウザから任意のプロンプト、パス、作業ディレクトリは送れない
- サーバーは `nohup` でバックグラウンド起動するので、本コマンドの完了後もブラウザでアクセスできる

## 失敗時の対応

- `bootstrap.sh` が pip install で失敗した場合: ユーザーに「ネットワーク接続を確認してください」と案内 + ログ末尾を表示
- ポート 8765-8774 すべて埋まっている場合: ユーザーに「他のサーバーが多数稼働しています。`--port <n>` で空きポートを指定してください」と案内
- 起動はできたが「Running on」が見えない場合: `tail -n 30 .study-server.log` を見て報告

`$ARGUMENTS`
