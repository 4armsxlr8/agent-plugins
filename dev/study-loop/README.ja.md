# study-loop（開発中）

English version → [README.md](README.md)

> **⚠️ 未リリースです。** このプラグインは意図的に `dev/` 配下に置いてあります。marketplace から外してあるため `/plugin install study-loop@agent-plugins` は動作せず、コマンド・ファイル形式・挙動は予告なく変わります。以下はすべて現時点の開発スナップショットの説明です。

「○○を勉強したい」を、解説を垂れ流すのではなくループに変えるスキルです。レベル診断 → 課題ファイル生成 → ユーザーが回答欄に記入 → 採点 → フィードバック → 次の課題、という流れを繰り返します。プログラミング・語学・数学・歴史・資格試験など、トピックを選びません。

主な構成要素:

- **`skills/study-loop/SKILL.md`** — オーケストレーション本体。Setup → Diagnostic（診断）→ Curriculum Generation（カリキュラム生成）→ Lesson Loop（学習ループ）の4フェーズを回し、セッション状態を `.study/<topic-slug>/` 配下に Markdown として保存します（進捗ダッシュボード、カリキュラム、用語集、フィードバックルール、気づきログなど）。
- **エビデンスベース設計** — すべての設計判断はメタ分析・システマティックレビューに基づき、効果サイズと出典が `skills/study-loop/references/learning-science.md` に記録されています。例: フィードバックの質（Hattie & Timperley、*d* ≈ 0.70–1.00）、Retrieval Practice / テスト効果（Roediger & Karpicke、*d* ≈ 0.50–0.80）、Self-Explanation 効果（Bisra et al.、*g* ≈ 0.55）、Worked Example の段階的な手放し（Sweller / Kalyuga、*d* ≈ 0.5–1.0）、分散学習・spacing（Cepeda et al.、*d* ≈ 0.4–0.9）、Interleaved Practice（Brunmair & Richter、*g* ≈ 0.42）、Elaborative Interrogation（Dunlosky et al.、*d* ≈ 0.42）。
- **Generator-Critic ループ** — 課題は Generator が下書きし、独立した Critic パスが検証してからユーザーに提示されます。解答がコメントに漏れているといった問題を1パス生成より確実に防ぎます。
- **`/study-ui`** — ローカルの Flask 製 Web UI（`skills/study-loop/scripts/server.py`）を loopback（127.0.0.1）限定で起動し、Markdown を直接編集する代わりにブラウザで lesson の閲覧・回答記入ができます。起動時にデフォルトブラウザが自動で開きます（`--no-open` で抑止可）。任意でローカルの Codex App Server セッションを介した採点にも対応。`/study-ui-stop` で停止します。

## clone して試す

インストールせずに Claude Code セッションへ読み込む:

```bash
claude --plugin-dir ./dev/study-loop
```

## Claude Code を使わずに Web UI を単独起動する

Web UI サーバーは Claude Code に一切依存していません。`start.sh` / `bootstrap.sh` / `stop.sh` / `server.py` はいずれも `CLAUDE_PLUGIN_ROOT` などの Claude Code 由来の環境変数を参照せず、`start.sh` が自前で Python の venv を構築します。リポジトリルートから次を実行します。

```bash
bash dev/study-loop/skills/study-loop/scripts/start.sh
```

初回実行時は `start.sh` が `bootstrap.sh` を呼び出し、スクリプトと同じ場所に `.venv` を作成して `flask` / `markdown` / `pymdown-extensions` を自動でインストールします。手動セットアップは不要です。

`--backend` は UI が Codex をどう扱うかを決めるフラグです（既定は `auto`）。

- `auto`（既定） — UI で明示的に開始操作（診断開始・採点など）を選んだときだけ Codex を起動します。ページを開いただけ、Markdown を保存しただけでは起動しません。
- `codex` — 現状の実装では `auto` と同じ挙動です。サーバー起動時ではなく UI で操作を選んだときだけ Codex を起動する点は変わりません。
- `manual` — Codex を一切使いません。すべての採点は Markdown だけを正とする手動フロー（回答ファイルを編集し、Claude Code など別のエージェントに採点してもらう）で行います。

Codex を使う場合の前提は、事前に一度 `codex login` を済ませてあることだけです。Codex のプロセスをあらかじめ起動しておく必要はありません。ジョブが Codex を必要とするタイミングで `codex_app_server.py` が自分で `codex app-server --stdio` をサブプロセスとして起動し、接続時に認証状態を確認します。ログインしていない場合は「Codex にログインしていません。`codex login` を実行してください。」と UI に表示され、手動フローにフォールバックします。

その他のフラグ:

- `--port <n>` — 固定ポート。指定しない場合、`start.sh` は 8765 から 8774 まで空きポートを自動で探します。指定した場合は衝突しても別ポートへは自動シフトしません。
- `--root <path>` — Study Loop セッションディレクトリのパス（既定: `$PWD/.study`）。
- `--host <addr>` — bind するアドレス（既定 `127.0.0.1`）。loopback アドレス（`127.0.0.1` / `localhost` / `::1`）のみ指定できます。
- `--no-open` — 起動後にブラウザを自動で開きません（既定は `open` / `xdg-open` で自動的に開きます）。

停止するには次を実行します。

```bash
bash dev/study-loop/skills/study-loop/scripts/stop.sh
```
