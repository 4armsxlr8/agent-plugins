# flutter-riverpod-guardrails

Flutter + Riverpod プロジェクトで Clean Architecture のレイヤー分離（Domain / Data / Application / Presentation）を守らせる Claude Code / Codex プラグインです。エージェントがファイルを編集した直後にレイヤー違反を検査し、`git commit` の前に `dart analyze` を実行します。

## 構成

- **`skills/architecture/`** — レイヤー依存ルールの知識スキル。Domain は Flutter / Riverpod / Firebase / http の import を禁止した純粋な Dart に保つ、Presentation は Data のリポジトリを直接 import しない、といったルールと、レイヤーごとのリファレンス・推奨ディレクトリ構成を定義します
- **`skills/lint-setup/`** — `import_lint` と `riverpod_lint` を導入して、レイヤー境界の強制を lint 設定として恒久化するセットアップスキル
- **`hooks/hooks.json`** — 2つの hook を配線します。Edit/Write 直後の `PostToolUse` hook が `scripts/check-architecture.sh` で変更ファイルのレイヤー違反を検出し、Bash の `PreToolUse` hook が `git commit` の前に `scripts/pre-commit-lint.sh` を実行します
- **`scripts/check-architecture.sh`** — レイヤー別の禁止 import、誤ったレイヤーでの `BuildContext` / `Navigator` 使用、Presentation での関数型ウィジェットなどをパターンマッチで検査します。スタンドアロン実行も可能です: `./check-architecture.sh --scan <lib_directory>`
- **`scripts/pre-commit-lint.sh`** — `git commit` の前に `dart analyze` を実行し、エラー・警告をエージェントに知らせます

## インストール

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install flutter-riverpod-guardrails@agent-plugins
```
