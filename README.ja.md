# agent-plugins

English version → [README.md](README.md)

Claude Code のプラグイン・スキルを公開する個人コレクションです。Codex のプラグイン形式にも対応しています。

## インストール

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

## プラグイン

### flutter-riverpod-guardrails — Flutter + Riverpod アーキテクチャ guardrail

Flutter + Riverpod プロジェクトで Clean Architecture のレイヤー分離（Domain / Data / Application / Presentation）を強制し、コミット前に `dart analyze` を実行するプラグインです。

主な構成要素:

- **`skills/architecture/SKILL.md`** — レイヤー依存ルールを定義します（例: Domain は Flutter / Riverpod / Firebase / http の import を一切禁止した純粋な Dart に保つ、Presentation は Data のリポジトリを直接 import しない、など）。レイヤーごとのリファレンスガイドと推奨ディレクトリ構成も含みます。
- **`hooks/hooks.json`** — 2つの hook を配線しています。Edit/Write 直後の `PostToolUse` hook が `scripts/check-architecture.sh` を実行して変更ファイルのレイヤー違反を検出し、Bash の `PreToolUse` hook が `git commit` コマンドの前に `scripts/pre-commit-lint.sh` を実行します。
- **`scripts/check-architecture.sh`** — レイヤー別の禁止 import、誤ったレイヤーでの `BuildContext` / `Navigator` 使用、Presentation での関数型ウィジェットなどをパターンマッチで検査します。`./check-architecture.sh --scan <lib_directory>` でスタンドアロンのスキャンモードとしても実行可能です。
- **`scripts/pre-commit-lint.sh`** — `git commit` の前に `dart analyze` を実行し、エラー・警告をエージェントに知らせます。

### crystallize — plan駆動開発フロー

対話から確定事項を1つずつ析出させて plan に結晶化し、その plan を機械ゲート・挙動ゲート・例外ゲートの3つに通してからコミットへ結晶化させる、開発フロー一式をまとめたプラグインです。

主な構成要素:

- **`skills/issue-create`** — 会話で出たバグ・思いつき・雑務を、テンプレに沿った GitHub issue として起票します。
- **`skills/find-unknowns`** — 実装着手前の認識合わせ。unknowns を洗い出してユーザーと潰し、plan を1枚作ります。
- **`skills/question-evaluator`** — `find-unknowns` がユーザーに出す質問の前提・二択の正当性を、出題側とは別コンテキストで監査します。
- **`skills/plan-implement`** — plan を受け取り、実装から機械・挙動・例外の3つのゲート、コミットへの引き継ぎまでを一続きで駆動します。
- **`skills/test-generator`** / **`skills/code-generator`** — TDD の red 側と green 側を別サブエージェントに分け、同じエージェントがテストと辻褄合わせの実装を両方書けないようにします。
- **`skills/diff-review`** — 動作確認が済んだあとの差分から、危険な箇所だけを人間に見せる例外ビューアです。
- **`skills/html-report`** — 長い散文の報告を自己完結 HTML レポートに整形します。
- **`skills/plan-commit`** — plan の内容をそのままコミットメッセージにしてコミットし、plan ファイルを削除します。
- **`skills/tdd`** — 残す価値のあるテストとは何かのリファレンスです。[mattpocock/skills](https://github.com/mattpocock/skills)（MIT）からのフォークです。

plan とレポートは、対象リポジトリの `docs/crystallize/plans/` と `docs/crystallize/reports/` に生成されます。

## 開発中（未リリース）

### study-loop — 任意トピックの段階的学習

「○○を勉強したい」を、解説を垂れ流すのではなくループに変えるスキルです。レベル診断 → 課題ファイル → 回答記入 → 採点 → フィードバック → 次の課題、という流れをローカルの Web UI 付きで繰り返します。[`dev/study-loop`](dev/study-loop) 配下にあります。

**まだ使えません。** marketplace から意図的に外してあるため `/plugin install study-loop@agent-plugins` は動作せず、コマンド・ファイル形式・挙動は予告なく変わります。それでも開発中の中身を覗いてみたい場合は、clone した上で `claude --plugin-dir ./dev/study-loop` で読み込めます（自己責任でお願いします）。

## ローカルでの開発・検証

インストールせずにリポジトリルートから直接読み込んでテストする:

```bash
claude --plugin-dir ./plugins/flutter-riverpod-guardrails
```

または、この checkout をローカル marketplace として登録する:

```bash
/plugin marketplace add /path/to/agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```

plugin.json / frontmatter / hooks.json のスキーマ・構文チェック:

```bash
claude plugin validate ./plugins/flutter-riverpod-guardrails
```

## ライセンス

MIT — [LICENSE](LICENSE) を参照。
