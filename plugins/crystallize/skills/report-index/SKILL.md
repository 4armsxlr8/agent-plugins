---
name: report-index
description: >-
  「レポート一覧」「レポートを一覧で」で発動。
  html-report / diff-review が生成した HTML レポートを、プロジェクト横断でブラウザに一覧表示するとき。
user-invocable: true
argument-hint: "[--port <番号>] (省略時は 47311 または $CRYSTALLIZE_REPORT_PORT)"
metadata:
  purpose: produce
  trigger: user
  shape: atomic
---

# report-index — レポート一覧をローカルサーバーで開く

`docs/crystallize/reports/` に保存された HTML レポートを、登録済みプロジェクトを横断して 1 つの画面に一覧表示する。一覧はリクエスト時に生成されるため、レポートが増えても再作成する必要はない。サブエージェントは fork せず、1 つのコマンドを実行して結果を中継するのみとする。

## Input / Output

- **Input**: `$ARGUMENTS` = 任意で `--port <番号>`。省略時は `$CRYSTALLIZE_REPORT_PORT`、それも無ければ 47311
- **Output**: ブラウザで `http://127.0.0.1:<port>/` を開く。最終応答は `ensure` が stdout に出力する URL と `projects=<登録プロジェクト数>` の 2 行をそのまま返す

## 仕組み (1 行ずつ)

- サーバーは `<skill-dir>/scripts/report_server.py` である (Python 標準ライブラリのみを使用し、127.0.0.1 のみに bind する)
- 走査対象のプロジェクトは registry ファイルで登録する。html-report と diff-review が保存時に自身のプロジェクトを登録するため、一覧には対象プロジェクトが自動的に追加される
- registry と state の保存先は `~/.crystallize/` を第一候補とし、書き込めない場合は `/tmp/claude/crystallize/`、それも使用できない場合は `$TMPDIR/crystallize/` を使用する。読み込む際はすべての保存先の内容を合算する

## Step 1: 起動して開く

```bash
PROJROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
python3 "<skill-dir>/scripts/report_server.py" ensure --root "$PROJROOT" --open   # $ARGUMENTS に --port があればそのまま末尾に付ける
```

`<skill-dir>` はスキル本文の先頭に注入される「Base directory for this skill」の絶対パス。`${CLAUDE_PLUGIN_ROOT}` は Bash では空になる (実測) ので使わない。

終了コードで分岐する:

| exit | 意味 | 次にすること |
|---|---|---|
| 0 | 起動済み (または今回起動した)。stdout に URL と `projects=N` が出力される | Step 2 へ |
| 3 | 起動した子プロセスがポートの bind を sandbox に拒否された (ログの末尾で判定済み) | **同じコマンドを sandbox を無効にして 1 回だけ再実行する** (サーバーの起動のみ sandbox の外で行う必要がある。2 回目以降の呼び出しは sandbox 内で実行できる) |
| 2 | ポートが別のプロセスに使用されている、`--root` が指定されていない、登録先に書き込めない等。stderr に理由が出力される | ポートが使用中なら `--port <別の番号>` を付けて再実行する。それ以外は理由をそのまま伝えて終了する |

sandbox を無効にした再実行も拒否された場合は、ユーザーに次のコマンドを案内して終了する (`!` 接頭辞はユーザー自身のシェルで実行される。`nohup … &` でバックグラウンド実行しないとシェルがサーバープロセスに占有される):

```
! nohup python3 <skill-dir>/scripts/report_server.py serve >/dev/null 2>&1 &
```

## Step 2: 最終応答

`ensure` の stdout (URL の行と `projects=N` の行) をそのまま返す。一覧の内容をチャットに転記しない。ブラウザ画面で確認したほうが検索や絞り込みを迅速に行えるためである。

## Gotchas

- **sandbox 内では bind・loopback 接続・ホームへの書き込みがすべて拒否される** (実測)。そのため起動確認は HTTP ではなく、サーバープロセスが保持している `server-<port>.lock` の flock を読み取り用ファイルディスクリプタで試行することで行い (PID の再利用や SIGKILL による終了後の残存ファイルによる誤判定を防ぐため。読み取り専用で開けば sandbox 内でも検証できる)、登録は HTTP ではなくファイルで行う。この設計を「healthz を curl する」方式に変更すると、sandbox 内で毎回失敗する
- プラグインを更新しても起動中のサーバーは古いコードのまま稼働する。`ensure` は state の version と自身の version を比較し、一致しなければサーバーを停止して再起動する。sandbox 内から停止できなかった場合は stderr にその旨が出力されるため、sandbox の外で `stop` を実行する
- ポートが別のプロセスに使用されていると `serve` は exit 2 で終了する。`--port` または `CRYSTALLIZE_REPORT_PORT` で別のポート番号を指定する。state と lock はポートごと (`server-<port>.json` / `.lock`) に管理されるため、別ポートを指定すれば 2 つ目のサーバープロセスが起動する。`status` / `stop` は全ポート分を対象に処理する
- `/tmp/claude/` に保存された registry は OS の一時ファイル削除によって消去されることがある。消去された場合でも次に html-report を実行したプロジェクトから再登録されるため、恒久的な登録が必要な場合は sandbox の外で `register --root` を 1 回実行する (サーバー自身も起動時に読み取れた登録情報を `~/.crystallize/roots/` へコピーする)
- 一覧のスタイルは html-report の `assets/style.css` をそのまま読み込み、一覧行の CSS だけをスクリプト内に保持する。style.css 側を修正しても component-samples.html の更新は不要である (一覧行の CSS は共通スタイル定義の外に置く設計としている。一覧はレポートそのものではなく、LLM が毎回生成する対象でもないためである)

## Additional resources

- `scripts/report_server.py` — サーバー本体。`serve` / `register` / `status` / `ensure` / `stop` の 5 つのサブコマンドがある。`python3 scripts/report_server.py -h`
