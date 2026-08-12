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

- **`skills/flutter-riverpod-architecture/SKILL.md`** — レイヤー依存ルールを定義します（例: Domain は Flutter / Riverpod / Firebase / http の import を一切禁止した純粋な Dart に保つ、Presentation は Data のリポジトリを直接 import しない、など）。レイヤーごとのリファレンスガイドと推奨ディレクトリ構成も含みます。
- **`hooks/hooks.json`** — 2つの hook を配線しています。Edit/Write 直後の `PostToolUse` hook が `scripts/check-architecture.sh` を実行して変更ファイルのレイヤー違反を検出し、Bash の `PreToolUse` hook が `git commit` コマンドの前に `scripts/pre-commit-lint.sh` を実行します。
- **`scripts/check-architecture.sh`** — レイヤー別の禁止 import、誤ったレイヤーでの `BuildContext` / `Navigator` 使用、Presentation での関数型ウィジェットなどをパターンマッチで検査します。`./check-architecture.sh --scan <lib_directory>` でスタンドアロンのスキャンモードとしても実行可能です。
- **`scripts/pre-commit-lint.sh`** — `git commit` の前に `dart analyze` を実行し、エラー・警告をエージェントに知らせます。

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
