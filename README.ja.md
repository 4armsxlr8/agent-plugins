# agent-plugins

English version → [README.md](README.md)

Claude Code のプラグイン・スキルを公開する個人コレクションです。Codex のプラグイン形式にも対応しています。

## インストール

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install study-loop@agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

## プラグイン

### study-loop — 任意トピックの段階的学習

「○○を勉強したい」を、解説を垂れ流すのではなくループに変えるスキルです。レベル診断 → 課題ファイル生成 → ユーザーが回答欄に記入 → 採点 → フィードバック → 次の課題、という流れを繰り返します。プログラミング・語学・数学・歴史・資格試験など、トピックを選びません。

主な構成要素:

- **`skills/study-loop/SKILL.md`** — オーケストレーション本体。Setup → Diagnostic（診断）→ Curriculum Generation（カリキュラム生成）→ Lesson Loop（学習ループ）の4フェーズを回し、セッション状態を `.study/<topic-slug>/` 配下に Markdown として保存します（進捗ダッシュボード、カリキュラム、用語集、フィードバックルール、気づきログなど）。
- **エビデンスベース設計** — すべての設計判断はメタ分析・システマティックレビューに基づき、効果サイズと出典が `skills/study-loop/references/learning-science.md` に記録されています。例: フィードバックの質（Hattie & Timperley、*d* ≈ 0.70–1.00）、Retrieval Practice / テスト効果（Roediger & Karpicke、*d* ≈ 0.50–0.80）、Self-Explanation 効果（Bisra et al.、*g* ≈ 0.55）、Worked Example の段階的な手放し（Sweller / Kalyuga、*d* ≈ 0.5–1.0）、分散学習・spacing（Cepeda et al.、*d* ≈ 0.4–0.9）、Interleaved Practice（Brunmair & Richter、*g* ≈ 0.42）、Elaborative Interrogation（Dunlosky et al.、*d* ≈ 0.42）。
- **Generator-Critic ループ** — 課題は Generator が下書きし、独立した Critic パスが検証してからユーザーに提示されます。解答がコメントに漏れているといった問題を1パス生成より確実に防ぎます。
- **`/study-ui`** — ローカルの Flask 製 Web UI（`skills/study-loop/scripts/server.py`）を loopback（127.0.0.1）限定で起動し、Markdown を直接編集する代わりにブラウザで lesson の閲覧・回答記入ができます。任意でローカルの Codex App Server セッションを介した採点にも対応。`/study-ui-stop` で停止します。

### flutter-riverpod-guardrails — Flutter + Riverpod アーキテクチャ guardrail

Flutter + Riverpod プロジェクトで Clean Architecture のレイヤー分離（Domain / Data / Application / Presentation）を強制し、コミット前に `dart analyze` を実行するプラグインです。

主な構成要素:

- **`skills/flutter-riverpod-architecture/SKILL.md`** — レイヤー依存ルールを定義します（例: Domain は Flutter / Riverpod / Firebase / http の import を一切禁止した純粋な Dart に保つ、Presentation は Data のリポジトリを直接 import しない、など）。レイヤーごとのリファレンスガイドと推奨ディレクトリ構成も含みます。
- **`hooks/hooks.json`** — 2つの hook を配線しています。Edit/Write 直後の `PostToolUse` hook が `scripts/check-architecture.sh` を実行して変更ファイルのレイヤー違反を検出し、Bash の `PreToolUse` hook が `git commit` コマンドの前に `scripts/pre-commit-lint.sh` を実行します。
- **`scripts/check-architecture.sh`** — レイヤー別の禁止 import、誤ったレイヤーでの `BuildContext` / `Navigator` 使用、Presentation での関数型ウィジェットなどをパターンマッチで検査します。`./check-architecture.sh --scan <lib_directory>` でスタンドアロンのスキャンモードとしても実行可能です。
- **`scripts/pre-commit-lint.sh`** — `git commit` の前に `dart analyze` を実行し、エラー・警告をエージェントに知らせます。

## ローカルでの開発・検証

インストールせずにリポジトリルートから直接読み込んでテストする:

```bash
claude --plugin-dir ./plugins/study-loop
claude --plugin-dir ./plugins/flutter-riverpod-guardrails
```

または、この checkout をローカル marketplace として登録する:

```bash
/plugin marketplace add /path/to/agent-plugins
/plugin install study-loop@agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

plugin.json / frontmatter / hooks.json のスキーマ・構文チェック:

```bash
claude plugin validate ./plugins/study-loop
claude plugin validate ./plugins/flutter-riverpod-guardrails
```

## ライセンス

MIT — [LICENSE](LICENSE) を参照。
