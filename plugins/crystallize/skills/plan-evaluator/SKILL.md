---
name: plan-evaluator
description: 「plan監査」「planレビュー」で発動。plan スキルが書いた plan の前提と受け入れ基準の網羅を採点する evaluator
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

`plan` スキルが書き出す plan (`docs/crystallize/plans/<slug>.md`) を、作成側とは独立したコンテキストで監査する評価者。plan は作成側セッションの確信から書かれるため、未検証の前提・spec の受け入れ基準の取りこぼしをそのまま含む — 実装セッションに渡る前に検出する。

- **plan・spec・呼び出し元スキル・評価基準を修正しない (Read のみ)** — 評価をパスする最短経路として基準側を書き換える誘惑を構造的に断つ (評価基準の保護原則)
- **spec は読む**。plan 先頭の `spec:` 行が指すファイルを `project_dir` (フォールバック時はカレントディレクトリ) 基準で解決して Read する — plan が spec の受け入れ基準をすべて覆っているかは、spec を読まなければ判定できない。**`spec:` 行が無い旧形式の plan は、plan 内の受け入れ基準を spec の代わりに使って通常どおり採点する** (`plan-implement` と `diff-review` が同じ互換を約束しているため、evaluator だけが落とすと旧 plan が実装に進めなくなる)。`spec:` 行も plan 内の受け入れ基準も無い場合にだけ `acceptance_coverage` を 0 とし、算定不能の理由を feedback に明記する。`spec:` 行が指すファイルが存在しない場合 (パスの誤り) は `structure_completeness` を減点する
- **ledger・impact.md・モックは、渡されても読まない** — 作成側の思考過程を見た監査者は同じバイアスに迎合する。plan + spec だけで監査することが plan の自己完結性の検査を兼ねる。コードベース本体の探索は前提の事実確認のためにむしろ必須
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

`plan` スキルの構成 5 要素が揃っているかを確認する:

1. ゴール 1 文が先頭行にある
2. `spec:` 行が spec のパスを指している
3. 守るべき既存挙動
4. 実装計画が変わりやすい順に並んでいる (ユーザーが差し替えたくなるものが先頭、機械的作業が末尾)。**各項目に対応する受け入れ基準 ID (AC-n) と TDD 対象 / 対象外が添えてある**
5. 検証コマンド (テスト・lint) と Deviations 規約

要件・受け入れ基準そのものが plan に転記されていても減点しない (旧形式の plan との互換)。ただし spec と食い違っていれば二重管理として medium 指摘にする。

### 2. 前提の抽出と分類

守るべき既存挙動・実装計画から前提を列挙し、2 種に分類する。

- **検証可能**: コードベース・ドキュメントで真偽が決まる主張 (「既存の認証は X 方式」「A モジュールは B に依存していない」等)
- **ユーザー選好**: 認識合わせでユーザーが決めた好み・優先順位

分類を省略しない — 選好を「未検証前提」として減点すると正当な plan を落とす偽陽性になる。**選好の正本は spec の「要件」節にある**ので、spec に書かれている記述は選好として扱い、裏取りの対象から外す。選好はそのまま受け入れ、検証可能な主張だけを手順 3 へ回す。

### 3. 検証可能な前提の事実確認

確からしく見えても必ず裏取りする — コードベースで検証できるものは Grep / Read / Explore subagent、API 仕様・ライブラリの機能有無・プラットフォーム制約など一般技術知識に属するものは WebSearch / WebFetch / 公式ドキュメントで。LLM は知識境界を正確に把握できず、もっともらしい誤前提を高い確信度で保持するため。

plan の検証コマンドは実行せず、静的に確かめる (package.json / Makefile 等と突き合わせてコマンドが実在するか) — 実行は Read-only 原則に反する。

### 4. 受け入れ基準の被覆

spec の「受け入れ基準 (テストケース表)」の**各行**を列挙し、対応する実装計画項目を突き合わせる。

- 対応する項目がない行があれば、その行を名指しで指摘する — 実装されない基準は、実装セッションでテストが書かれないまま通過する
- 「テストしないと決めたもの」に該当する行を実装計画が TDD 対象として扱っていないか (逆も同じ)
- spec の「実機確認に委ねる基準」に対応する項目は TDD 対象外になっているか
- 受け入れ基準の妥当性そのもの (観測可能か・境界を網羅しているか) は採点しない — それは spec の責務で、spec の妥当性はユーザーの反応が担保する。ここで採点すると、ユーザーが合意した基準を監査者が上書きすることになる

### 5. 自己完結性と並び順

- plan + spec だけで実装に入れるか — ledger・impact.md 等の作業ファイルを読まないと意味が取れない記述がないか
- `plans/<slug>/` 配下への相対リンク (plan-commit 後にリンク切れとして履歴に残る) がないか。`specs/<slug>.md` へのリンクは可 (spec は残るファイル)
- 実装計画が変わりやすい順に並んでいるか (ユーザーは先頭だけ精読すればよい、という設計が成立しているか)

### 6. フィードバックと eval JSON

Markdown フィードバック (構成要素の充足表 / 前提の検証結果 / 受け入れ基準の被覆表 / 自己完結性 / 総評) を出し、eval JSON を書き出す。`passed: false` の場合は必ず `rewrite` に修正案を入れる — **plan 全文の書き直しではなく、修正すべき見出し単位の置換案** (見出し名 + 置き換え後の文面)。全文を書き直すと監査者自身の未検証前提が混入する。

## eval JSON schema

```json
{
  "score": <quality.overall と同値の 0-100>,
  "plan_implementation": {"overall": 100, "notes": "plan 監査では実装との突き合わせは対象外"},
  "quality": {
    "overall": <0-100>,
    "breakdown": {
      "premise_grounding": <0-100>,
      "acceptance_coverage": <0-100>,
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

基準の正本は `plan` SKILL.md「3. plan の書き出し」の構成規則。同節が改訂されたら本表と `eval-schema.json` を追随させる。

| breakdown キー | 評価内容 | 根拠 |
|---------------|---------|------|
| `premise_grounding` | 検証可能な前提が事実 (コードベース、または一般技術知識なら Web / 公式ドキュメント) と一致するか。裏取りせず確信だけで通した前提があれば減点。ユーザー選好 (spec の要件節にあるもの) は対象外 | plan 構成「守るべき既存挙動」「実装計画」 |
| `acceptance_coverage` | spec の受け入れ基準の各行が、いずれかの実装計画項目に対応しているか。対応しない行があれば減点。基準そのものの妥当性は採点しない (spec 側の責務) | plan 構成「実装計画」の受け入れ基準対応 |
| `structure_completeness` | 構成 5 要素 (ゴール 1 文 / `spec:` 行 / 守るべき既存挙動 / 実装計画 / 検証コマンド + Deviations 規約) と、各項目の受け入れ基準対応・TDD 適否の併記が揃っているか。併記の検査は寛容に — 皆無なら減点、個々の項目の書き漏れは low 指摘に留める | plan 構成 1〜5 |
| `self_containedness` | plan + spec で実装に入れるか。作業ファイル依存・`plans/<slug>/` への相対リンクがないか (spec へのリンクは可) | plan Gotcha (相対リンク禁止) |
| `volatility_ordering` | 実装計画が変わりやすい順に並んでいるか | plan 構成「実装計画 (変わりやすい順)」 |

## Gotchas

- **「前提は正しそう」で裏取りを省略しない** — 監査の存在意義は作成側の確信を疑うことにある。作成側と同じ確信で通すなら監査は無意味
- **ユーザー選好を未検証前提として落とさない** — 認識合わせで決まった選好は監査対象外。spec の要件節にある記述は選好として扱う。手順 2 の分類を飛ばすと、ここで偽陽性が出て正当な plan を差し戻すことになる
- **spec の受け入れ基準に文句を付けない** — 監査するのは plan が基準を覆っているかであって、基準の中身の善し悪しではない。基準はユーザーが反応して確定させたもので、監査者はその反応を見ていない
- **rewrite で新しい前提を持ち込まない** — 置換案は検証済みの事実と plan・spec 内の既存記述だけで構成する。見出し単位に留めるのはこのため
- **網羅性の高さを加点しない** — 長く網羅的な plan は読まれない (`plan` スキルの設計思想)。要素の充足を検査するのであって、詳細さ・分量を採点しない
