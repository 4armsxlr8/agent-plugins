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

対話から要件を spec（残して育てる文書）に析出させ、spec から使い捨ての plan を作り、その plan を機械ゲート・挙動ゲート・例外ゲートの3つに通してからコミットへ結晶化させる、開発フロー一式をまとめたプラグインです。要件は固定するものではなく育てるものとして扱い、挙動ゲートでユーザーが「やっぱり違う」と言ったら逸脱ではなく spec の改訂として処理します。

主な構成要素:

- **`skills/issue-create`** — 会話で出たバグ・思いつき・雑務を、テンプレに沿った GitHub issue として起票します。
- **`skills/spec`** — 実装着手前の認識合わせ。前提が解決済みの質問を番号付きのラウンドで一括して出し（各質問に推奨回答つき）、構造の論点があるときだけモックで反応を取り、要件・非機能要件・受け入れ基準（テストケース表）を spec に書きます。既存 spec を渡せば改訂モードで育てます。
- **`skills/question-evaluator`** — `spec` がユーザーに出す質問の前提・二択の正当性を別コンテキストで監査します。既定では動かず、`audit: on` で任意に使います。
- **`skills/plan`** — spec から、変わりやすい順に並べた使い捨ての実装計画を作ります。spec が大きいときは、触るモジュールが重ならず単体で挙動確認できる単位でだけ複数の plan（= 複数コミット）に分けます。
- **`skills/plan-evaluator`** — plan が spec の受け入れ基準を全て覆っているか・前提が裏取りされているか・自己完結しているかを、作成側とは別コンテキストで監査します。
- **`skills/plan-implement`** — plan と spec を受け取り、実装から機械・挙動・例外の3つのゲート、コミットへの引き継ぎまでを一続きで駆動します。挙動ゲートでのユーザー発の変更は止めずに仕様改訂レーンで処理します。
- **`skills/test-generator`** / **`skills/code-generator`** — TDD の red 側と green 側を別サブエージェントに分け、同じエージェントがテストと辻褄合わせの実装を両方書けないようにします。RED は spec のテストケース表から直接書くので、実装開始時に seam の合意を取り直しません。
- **`skills/diff-review`** — 動作確認が済んだあとの差分から、昇格した箇所だけを決裁カード（何が起きうるか・戻せるか・影響範囲・AI レビューの判定）で見せ、コードは畳む例外ビューアです。昇格が 0 件なら画面を作らず 1 行で go を取ります。
- **`skills/html-report`** — 長い散文の報告を、要点先行の固定構成とインライン SVG の図解カタログで自己完結 HTML レポートに整形します。
- **`skills/plan-commit`** — plan の内容をそのままコミットメッセージにしてコミットし、plan ファイルを削除します。spec は残ります。
- **`skills/tdd`** — 残す価値のあるテストとは何かのリファレンスです。[mattpocock/skills](https://github.com/mattpocock/skills)（MIT）からのフォークです。

spec・plan・レポートは、対象リポジトリの `docs/crystallize/specs/`・`docs/crystallize/plans/`・`docs/crystallize/reports/` に生成されます。

### ui-craft — 目で見られないエージェントのための UI/UX デザイン知識

UI/UX のエッセンス——デザイナーが経験則として持っている「なんとなく美しい／なんとなく揃っていない」の判断——を、目で見ることのできないエージェントが実行できる形に翻訳したスキル集です。翻訳の中身は「数値の初期値」「トークンでの書き方」「スクリーンショットでの検証手順」の3点。スキルは今後増やしていく前提で、現在は `visual-adjustment`（錯視補正）の1本のみです。

主な構成要素:

- **`skills/visual-adjustment/SKILL.md`** — 上方距離過大の錯視 / 色の面積効果 / 三角形分割錯視（重心揃え） / 形による見かけの大きさ / オーバーシュート / 密度と重心 / ハーマングリッドの7項目について、それぞれ初期値・トークンでの補正の書き方・二重補正への注意点をまとめます。発動ワードは「錯視補正」「視覚調整」。モック作成や UI 実装で余白・色・アイコン配置を「揃える」判断をする場面でも自動発動します。
- **`skills/visual-adjustment/references/sources.md`** — SKILL.md の各数値がどこから来ているか（原佑一氏（CyberAgent / Ameba）の Speaker Deck、Bjango の光学補正の公式、Material Design の icon keyline など）を、出典あり・幾何計算・経験則のいずれかに区分して対応させた一覧です。

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
