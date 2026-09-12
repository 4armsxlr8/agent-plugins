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

`docs/crystallize/reports/` に溜まった HTML レポートを、登録済みプロジェクトを横断して 1 画面に並べる。一覧はリクエスト時に生成されるので、レポートが増えても作り直しは要らない。fork しない — やることは 1 コマンドの実行と結果の中継だけ。

## Input / Output

- **Input**: `$ARGUMENTS` = 任意で `--port <番号>`。省略時は `$CRYSTALLIZE_REPORT_PORT`、それも無ければ 47311
- **Output**: ブラウザで `http://127.0.0.1:<port>/` を開く。最終応答は `ensure` が stdout に出す URL と `projects=<登録プロジェクト数>` の 2 行を写すだけ

## 仕組み (1 行ずつ)

- サーバーは `<skill-dir>/scripts/report_server.py` (Python 標準ライブラリのみ、127.0.0.1 にしか bind しない)
- 走査対象のプロジェクトは registry ファイルで登録する。html-report と diff-review が保存時に自分のプロジェクトを登録するので、一覧は使うほど勝手に育つ
- registry と state の置き場は `~/.crystallize/` を第一候補に、書けなければ `/tmp/claude/crystallize/`、それも駄目なら `$TMPDIR/crystallize/` へ落ちる。読むときは全部を合算する

## Step 1: 起動して開く

```bash
PROJROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
python3 "<skill-dir>/scripts/report_server.py" ensure --root "$PROJROOT" --open   # $ARGUMENTS に --port があればそのまま末尾に付ける
```

`<skill-dir>` はスキル本文の先頭に注入される「Base directory for this skill」の絶対パス。`${CLAUDE_PLUGIN_ROOT}` は Bash では空になる (実測) ので使わない。

終了コードで分岐する:

| exit | 意味 | 次にすること |
|---|---|---|
| 0 | 起動済み (または今起動した)。stdout に URL と `projects=N` が出る | Step 2 へ |
| 3 | 起動した子プロセスがポートの bind を sandbox に拒否された (ログの末尾で判定済み) | **同じコマンドを sandbox を無効にして 1 回だけ再実行する** (サーバーの起動だけが sandbox の外を必要とする。2 回目以降の呼び出しは sandbox 内で済む) |
| 2 | ポートが別プロセスに使われている・`--root` が無い・登録先に書けない等。stderr に理由が出る | ポート使用中なら `--port <別の番号>` を付けて再実行する。それ以外は理由をそのまま伝えて終了する |

sandbox を外した再実行も断られたら、ユーザーに次を案内して終了する (`!` 接頭辞はユーザー自身のシェルで実行される。`nohup … &` で切り離さないとシェルがサーバーに占有される):

```
! nohup python3 <skill-dir>/scripts/report_server.py serve >/dev/null 2>&1 &
```

## Step 2: 最終応答

`ensure` の stdout (URL の行と `projects=N` の行) をそのまま返す。一覧の中身をチャットに書き写さない — 画面のほうが検索も絞り込みも速い。

## Gotchas

- **sandbox 内では bind・loopback 接続・ホームへの書き込みがすべて拒否される** (実測)。だから起動確認は HTTP ではなく、サーバーが握っている `server-<port>.lock` の flock を読み取り fd で試すことで行い (pid の再利用や SIGKILL 後の残骸に騙されない。読み取りで開けば sandbox 内でも試せる)、登録は HTTP ではなくファイルで行う。この設計を「healthz を curl する」形に戻すと sandbox 内で毎回失敗する
- プラグインを更新すると起動中のサーバーは古いコードのまま。`ensure` は state の version と自分の version を比べ、違えば止めて起動し直す。sandbox 内から止められなかったときは stderr にその旨が出るので、`stop` を sandbox の外で実行する
- ポートが別のプロセスに使われていると `serve` は exit 2 で止まる。`--port` か `CRYSTALLIZE_REPORT_PORT` で逃がす。state と lock はポートごと (`server-<port>.json` / `.lock`) なので、別ポートを指定すれば 2 台目が立つ。`status` / `stop` は全ポート分を扱う
- `/tmp/claude/` に落ちた registry は OS の一時ファイル掃除で消えることがある。消えても次に html-report を走らせたプロジェクトから再登録されるので、恒久的な登録が要るときは sandbox の外で `register --root` を 1 回実行する (サーバー自身も起動時に読めた登録を `~/.crystallize/roots/` へ写す)
- 一覧の見た目は html-report の `assets/style.css` をそのまま読み込み、一覧行の CSS だけをスクリプト内に持つ。style.css 側を直しても component-samples.html の貼り直しは不要 (一覧行の CSS は正本の外に置く判断をした — 一覧はレポートではなく、LLM が毎回生成するものでもないため)

## Additional resources

- `scripts/report_server.py` — サーバー本体。`serve` / `register` / `status` / `ensure` / `stop` の 5 サブコマンド。`python3 scripts/report_server.py -h`
