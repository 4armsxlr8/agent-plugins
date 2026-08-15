# crystallize

crystallize は plan 駆動開発フローをまとめた Claude Code プラグインです。ユーザーとの対話から確定事項を1つずつ析出させて `docs/crystallize/plans/` 配下の plan ファイル(結晶)にまとめ、その plan を「機械の門(テスト・lint・AI コードレビュー)」「挙動の門(ユーザー自身による動作確認)」「例外の門(危険箇所だけを見せる diff レビュー)」の3つの門に順に通してから、plan の内容をそのままコミットメッセージにして確定させます。認識合わせ・実装・検証・コミットまでを1本のフローとしてつなぐことで、曖昧な依頼が実装に流れ込む前に潰し、レビューは「全部読む」から「危ない箇所だけ読む」に絞ります。

## フロー

```
issue-create
  └─ 会話中のバグ・思いつき・雑務を GitHub issue に起票
      ↓
find-unknowns
  └─ unknowns(未知)を洗い出して潰し、plan (docs/crystallize/plans/<slug>.md) を作る
      ↓
plan-implement
  ├─ 実装 (TDD 対象は test-generator → code-generator、それ以外は code-generator)
  ├─ 機械の門   … テスト・lint・AI コードレビュー
  ├─ 挙動の門   … ユーザー自身が動かして「意図どおりか」を確認
  └─ 例外の門   … diff-review で危険箇所だけを人間に見せる
      ↓
plan-commit
  └─ plan の内容をコミットメッセージにして確定・plan ファイルを削除
```

## スキル一覧

| スキル | 内容 |
|---|---|
| `issue-create` | 会話で出たバグ・思いつき・雑務を GitHub issue として起票する。リポジトリ既存のテンプレ・ラベル運用に従い、何も設置しない |
| `find-unknowns` | 実装に入る前の認識合わせ。unknowns を洗い出して潰し、plan を1枚作る |
| `question-evaluator` | `find-unknowns` がユーザーに出す質問の前提・二択の正当性を、出題側とは別コンテキストで監査する |
| `plan-implement` | plan を受け取り、実装 → 機械の門 → 挙動の門 → 例外の門 → コミットまでを一続きで駆動する |
| `test-generator` | TDD 対象スライスの実装前に、失敗するテスト(RED)だけを書く |
| `code-generator` | スライスを実装して GREEN にする。レビュー指摘の修正でも使う |
| `diff-review` | 動作確認が収束したあとの差分から、危険な箇所だけを人間に見せるレビュー画面を作る |
| `html-report` | 30行を超える散文の報告を、自己完結 HTML レポートに整形して開く(`diff-review` の派生元) |
| `plan-commit` | plan の内容をそのままコミットメッセージにしてコミットし、plan ファイルを削除する |
| `tdd` | red → green のループから残す価値のあるテストを書くためのリファレンス |

## 成果物の保存先

- `docs/crystallize/plans/` — `find-unknowns` が作る plan と作業ファイル。plan は `plan-commit` でコミットメッセージに畳み込まれると同時に削除されるため、リポジトリの履歴には一時的にしか残りません
- `docs/crystallize/reports/` — `html-report` / `diff-review` が生成する HTML レポート

## tdd スキルの出所

`skills/tdd/` は [mattpocock/skills](https://github.com/mattpocock/skills)(MIT License)の [tdd スキル](https://github.com/mattpocock/skills/tree/main/skills/engineering/tdd)をフォークし、日本語化・改造したものです。

## インストール

```
/plugin marketplace add 4armsxlr8/agent-plugins
/plugin install crystallize@agent-plugins
```

### ローカルでの開発・検証

```bash
claude --plugin-dir ./plugins/crystallize
```

または、この checkout をローカル marketplace として登録する:

```bash
/plugin marketplace add /path/to/agent-plugins
/plugin install crystallize@agent-plugins
```
