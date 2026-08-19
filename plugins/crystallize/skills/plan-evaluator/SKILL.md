---
name: plan-evaluator
description: 「plan監査」「planレビュー」で発動。find-unknowns が書いた plan の前提と受け入れ基準を採点する evaluator
user-invocable: true
argument-hint: "<context-json path | plan path>"
context: fork
agent: general-purpose
metadata:
  purpose: judge
  trigger: both
  shape: forked
  role: evaluator
---

# plan-evaluator

find-unknowns が書き出す plan (`docs/crystallize/plans/<task-slug>.md`) を、作成側とは独立したコンテキストで監査する評価者。plan は作成側セッションの確信から書かれるため、未検証の前提・観測不能な受け入れ基準・境界の取りこぼしをそのまま含む — 実装セッションに渡る前に検出する。

- **plan・呼び出し元スキル・評価基準を修正しない (Read のみ)** — 評価をパスする最短経路として基準側を書き換える誘惑を構造的に断つ (評価基準の保護原則)
- **ledger・impact.md・モックは、渡されても読まない** — 作成側の結論を見た監査者は同じバイアスに迎合する。plan 単体で監査することが自己完結性の検査を兼ねる。コードベース本体の探索は前提の事実確認のためにむしろ必須
- **model は frontmatter で指定しない (= セッションモデルを継承)** — 評価者は作成側と同格以上に保つ。plan の修正は実装前なら安いが、監査の見逃しは実装後の手戻りとして高くつく

## 契約 (単一)

- **Input**: `$ARGUMENTS` = context JSON ファイルのパス (evaluator 単一契約)。JSON キーは `project_dir` / `plan` / `criteria` / `threshold` / `turns_dir` / `iteration` / `output_contract` (`eval_file` / `schema` / `instructions`)。監査対象の plan ファイルは `plan` で指定する
- **Output**: `output_contract.eval_file` に下記 eval JSON schema で Write する

### context JSON 不在時のフォールバック

`$ARGUMENTS` が context JSON として解釈できない場合 (JSON でない / ファイル不在 / `output_contract` が空):

- ファイルパスなら plan ファイルとして Read、それ以外は plan の生テキストとして扱う
- eval JSON の書き出し先は `{project_dir=カレントディレクトリ}/output/eval-<YYYYMMDD-HHMMSS>-plan-evaluator.json` (ディレクトリが無ければ作成)
- Markdown フィードバックは stdout に出し、末尾に同 schema の eval JSON を添付

## 手順

### 1. 構成要素の確認

find-unknowns Step 5 の構成 6 要素が揃っているかを確認する:

1. ゴール 1 文が先頭行にある
2. 確定事項 (テスト・lint の検証コマンド 1 行を含む)
3. 実装計画が変わりやすい順に並んでいる (ユーザーが差し替えたくなるものが先頭、機械的作業が末尾)
4. 守るべき既存挙動
5. 観測可能な受け入れ基準
6. Deviations 規約

### 2. 前提の抽出と分類

確定事項・守るべき既存挙動・実装計画から前提を列挙し、2 種に分類する。

- **検証可能**: コードベース・ドキュメントで真偽が決まる主張 (「既存の認証は X 方式」「A モジュールは B に依存していない」等)
- **ユーザー選好**: 認識合わせでユーザーが決めた好み・優先順位

分類を省略しない — plan の確定事項にはユーザーが決めた選好が多く含まれ、監査は ledger を読まないため選好の裏取り先が存在しない。選好を「未検証前提」として減点すると正当な plan を落とす偽陽性になる。選好はそのまま受け入れ、検証可能な主張だけを手順 3 へ回す。

### 3. 検証可能な前提の事実確認

確からしく見えても必ず裏取りする — コードベースで検証できるものは Grep / Read / Explore subagent、API 仕様・ライブラリの機能有無・プラットフォーム制約など一般技術知識に属するものは WebSearch / WebFetch / 公式ドキュメントで。LLM は知識境界を正確に把握できず、もっともらしい誤前提を高い確信度で保持するため。

確定事項の検証コマンドは実行せず、静的に確かめる (package.json / Makefile 等と突き合わせてコマンドが実在するか) — 実行は Read-only 原則に反する。

### 4. 受け入れ基準と境界

- 各基準が観測可能か — 「テスト全緑」「初回表示 3 秒以内」のような挙動レベルで書かれているか。「きれいに実装する」は基準ではない
- 挙動が変わる境界 — 数量の 0/1/多/上限、時刻の跨ぎ、中断・再実行、空・重複・順序 — のうち plan のスコープに該当するものが基準に含まれているか

### 5. 自己完結性と並び順

- plan 単体で実装に入れるか — ledger・impact.md 等の作業ファイルを読まないと意味が取れない記述や、作業ファイルへの相対リンク (plan-commit 後にリンク切れとして履歴に残る) がないか
- 実装計画が変わりやすい順に並んでいるか (ユーザーは先頭だけ精読すればよい、という設計が成立しているか)

### 6. フィードバックと eval JSON

Markdown フィードバック (構成要素の充足表 / 前提の検証結果 / 受け入れ基準・自己完結性 / 総評) を出し、eval JSON を書き出す。`passed: false` の場合は必ず `rewrite` に修正案を入れる — **plan 全文の書き直しではなく、修正すべき見出し単位の置換案** (見出し名 + 置き換え後の文面)。全文を書き直すと監査者自身の未検証前提が混入する。

## eval JSON schema

```json
{
  "score": <quality.overall と同値の 0-100>,
  "plan_implementation": {"overall": 100, "notes": "plan 監査では実装との突き合わせは対象外"},
  "quality": {
    "overall": <0-100>,
    "breakdown": {
      "premise_grounding": <0-100>,
      "acceptance_observability": <0-100>,
      "structure_completeness": <0-100>,
      "self_containedness": <0-100>,
      "volatility_ordering": <0-100>
    }
  },
  "feedback": "<high → medium → low を畳み込んだ string サマリ>",
  "feedback_structured": {
    "high":   [{"area": "<premise|acceptance|structure|self-containedness|ordering>", "message": "<指摘 + 根拠 (裏取りしたファイル:行)>"}],
    "medium": [{"area": "...", "message": "..."}],
    "low":    [{"area": "...", "message": "..."}]
  },
  "rewrite": "<見出し単位の置換案 (見出し名 + 置き換え後の文面)。passed: true なら null>",
  "passed": <bool>,
  "evaluator_skill": "plan-evaluator"
}
```

**passed の判定**: 検証可能な前提に誤りが 1 つでも確認されたら、score に関わらず `passed: false` (誤前提の plan は実装後の手戻りとして必ず跳ね返る)。それ以外は score >= threshold (context JSON 指定。フォールバック時は 80)。

## 採点観点の定義

基準の正本は `find-unknowns` SKILL.md「Step 5: plan の書き出し」の構成規則。同節が改訂されたら本表と `eval-schema.json` を追随させる。

| breakdown キー | 評価内容 | 根拠 |
|---------------|---------|------|
| `premise_grounding` | 検証可能な前提が事実 (コードベース、または一般技術知識なら Web / 公式ドキュメント) と一致するか。裏取りせず確信だけで通した前提があれば減点。ユーザー選好は対象外 | Step 5 構成 2 (確定事項) / 4 (守るべき既存挙動) |
| `acceptance_observability` | 受け入れ基準が観測可能な挙動レベルで書かれ、該当する境界を網羅しているか | Step 5 構成 5 (観測可能な受け入れ基準 + 境界の洗い出し) |
| `structure_completeness` | 構成 6 要素と検証コマンド 1 行が揃っているか | Step 5 構成 1〜6 |
| `self_containedness` | plan 単体で実装に入れるか。作業ファイル依存・相対リンクがないか | Step 5 冒頭の自己完結要件 + Gotcha (相対リンク禁止) |
| `volatility_ordering` | 実装計画が変わりやすい順に並んでいるか | Step 5 構成 3 (変わりやすい順) |

## Gotchas

- **「前提は正しそう」で裏取りを省略しない** — 監査の存在意義は作成側の確信を疑うことにある。作成側と同じ確信で通すなら監査は無意味
- **ユーザー選好を未検証前提として落とさない** — 認識合わせで決まった選好は監査対象外。手順 2 の分類を飛ばすと、ここで偽陽性が出て正当な plan を差し戻すことになる
- **rewrite で新しい前提を持ち込まない** — 置換案は検証済みの事実と plan 内の既存記述だけで構成する。見出し単位に留めるのはこのため
- **網羅性の高さを加点しない** — 長く網羅的な plan は読まれない (find-unknowns の設計思想)。要素の充足を検査するのであって、詳細さ・分量を採点しない
