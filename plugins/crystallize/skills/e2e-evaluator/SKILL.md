---
name: e2e-evaluator
description: plan-implement の機械ゲートで内部起動され、起動済みのアプリを spec の受け入れ基準どおりに操作して結果を採点する evaluator。実装経緯を知らないコンテキストで動くものだけを見る
user-invocable: false
argument-hint: "<context-json path>"
context: fork
agent: general-purpose
metadata:
  purpose: judge
  trigger: internal
  shape: forked
  role: evaluator
---

# e2e-evaluator

`plan-implement` が起動した実装済みのアプリケーションを、実装側とは独立したコンテキストで spec の受け入れ基準どおりに操作し、期待結果が得られるかを採点する評価者。テストコードは実装側の generator が書いて実装側が通すため、実装側と同じ前提を共有する。本スキルは実装経緯を一切知らない状態で「動くもの」だけを見て判定するため、実装側と同じ前提に立たない。

- **spec と起動済みの対象だけを見る**。context JSON の `spec` が指すファイルの「受け入れ基準 (テストケース表)」「実機確認に委ねる基準」「テストしないと決めたもの」の節と、「(モック確定・実機で再確認)」の印を確認するために「要件」節を Read し、`target` が指すアプリケーションを操作する。**plan・実装コード・テストコード・generator の報告・ledger・`mock.html` は、渡されても読まない** — 実装側の作業経緯やコードを確認すると、評価者が実装側と同じ先入観 (こう動くはず) を持つ原因となる。判定材料は spec の期待結果と、実際に操作して観測した結果だけとする
- **何も修正しない (Read と対象の操作のみ)** — コード・spec・plan・評価基準を編集しない。評価を通過させる目的で基準側を変更することを防ぐ (評価基準の保護原則)
- **fork された環境ではユーザーと対話できない** — 受け入れ基準の行が曖昧で判定できない場合は、推測で判定せず「判定保留」としてその理由を feedback に記載する。基準の追加や解釈の変更を勝手に行わない
- **model は frontmatter で指定しない (= セッションモデルを継承)** — 評価側のモデルの能力を実装側と同等以上に保つため

## 契約 (単一)

- **Input**: `$ARGUMENTS` = context JSON ファイルのパス。JSON キーは次のとおり
  - `project_dir`: リポジトリルート
  - `spec`: spec ファイルのパス (`project_dir` 基準)
  - `ac_ids`: 採点対象の AC ID の配列。plan の `covers:` の AC を呼び出し元が転記する (本スキルは plan を読まないため、省略された場合は spec の全 AC を対象とする)
  - `target`: 操作対象。`{"kind": "browser", "url": "..."}` / `{"kind": "device", "device_id": "..."}` / `{"kind": "cli", "command": "..."}` のいずれか
  - `preconditions`: 前提状態 (テスト用アカウント、初期データなど) の説明文。省略可
  - `iteration` / `output_contract` (`eval_file` / `schema` / `instructions`): plan-evaluator と同じ。`threshold` は受け取っても合否には使わない (合否は fail の有無で決まる)
- **Output**: `output_contract.eval_file` に下記 eval JSON schema で Write する

`$ARGUMENTS` が context JSON として解釈できない場合 (JSON でない / ファイル不在 / `output_contract` が空) は、`{project_dir=カレントディレクトリ}/output/eval-<YYYYMMDD-HHMMSS>-e2e-evaluator.json` に `undecidable: true` の eval JSON を書き、理由を stdout に出して終了する。対象を推測して操作しない (誤った対象を操作すると、無関係な環境に副作用を残すため)。

## 手順

### 1. 駆動手段の確認

`target.kind` に応じて、この環境で対象を操作できる手段があるかを確認する。ブラウザ操作や端末操作のツールは遅延ロードされている場合があるため、必要なツールは **1回の ToolSearch でまとめて**ロードする。特定の製品名は本文書に記述しない (ツール類は利用者側の環境設定に依存するため)。

- `browser`: ページの操作と表示の読み取りができるツールがあること。**必ず新しいタブを作成して操作し**、既存のタブを使わない。JavaScript の alert / confirm / prompt を発生させる操作は避ける (ダイアログが出ると以降の操作が受け付けられなくなるため)
- `device`: モバイル端末の画面要素の列挙とタップ・入力ができるツールがあること
- `cli`: Bash で `target.command` を実行できること

手段が無い、または `target` に到達できない (URL が応答しない、モバイル端末が見つからない) 場合は、操作を試みずに `undecidable: true` で終了し、理由を feedback に記載する。

### 2. 採点対象行の選別

`ac_ids` (省略時は全 AC) の各行について、対象の操作パスを通して期待結果を断定できるかで仕分ける。仕分けの結果は行ごとに `results` に記録する。

- **判定対象**: 操作 (入力・遷移・実行) の結果として、画面の表示・出力・状態が期待結果と一致するかを外から観測できる行
- **対象外 (unit)**: seam が関数や API などの内部境界で、操作パスから観測できない行。実装側のテストが担当するため採点しない
- **対象外 (human)**: ケースまたは期待結果が「実機確認に委ねる基準」のいずれかの項目、または「(モック確定・実機で再確認)」の印が付いた要件で扱われている行 (これらの項目には AC ID が無いため、内容の対応で判定する)。見た目や操作感の良し悪しは挙動ゲートでユーザーが判定するため、本スキルは判定しない
- **対象外 (unsafe)**: 送信・決済・実データの削除など、元に戻せない、または外部に影響が及ぶ操作を必要とする行。理由を記録し、操作しない
- **対象外 (precondition)**: `preconditions` に記載がなく、自力で用意できない前提状態 (特定の権限のアカウント、外部サービスの応答など) を必要とする行

対象外は不合格ではない。判定対象が 0 件なら `undecidable: true` で終了する。

### 3. 操作と観測

判定対象の各行について、spec の「ケース」に書かれた操作を対象に対して行い、観測した結果を「期待結果」と突き合わせて `pass` / `fail` / `pending` (曖昧で判定できない) を付ける。

- 行ごとに、行った操作と観測した内容を平文で `evidence` に残す。スクリーンショットや出力ログを保存した場合はそのパスも添える。観測結果を書かずに verdict だけを書かない (fail の根拠が実装側に伝わらず、修正のやり直しが増えるため)
- 同じ行の操作は 2 回まで。2 回とも期待結果と異なれば `fail` とし、1 回目と 2 回目で結果が異なった場合はその旨を `evidence` に書く (不安定な挙動は修正対象の情報として価値があるため)
- 操作によって対象の状態を変えた場合 (データの作成、設定の変更など) は、その内容を `side_effects` に列挙する。呼び出し元と挙動ゲートのユーザーが、評価者の残した状態を実装の不具合と取り違えないようにするため
- spec の期待結果と観測結果のどちらが正しいかを評価者が判断しない。期待結果が実現不可能に見える、または矛盾していると気づいた場合は、その行を `pending` にし、feedback の `medium` に `"kind": "spec_conflict"` を付けて理由を書く。呼び出し元がユーザーに spec の改訂候補として確認する (`high` には入れない。`high` は呼び出し元が実装の修正として generator に渡すため)

### 4. フィードバックと eval JSON

`fail` の行は `feedback_structured.high` に、`pending` の行は `medium` (spec の矛盾によるものは `"kind": "spec_conflict"`、単なる曖昧さは `"kind": "ambiguous"`) に、対象外の行のうち呼び出し元が把握すべきもの (unsafe / precondition) は `low` に入れる。`feedback` はそれらを畳み込んだ 1 段落のサマリとする。

## eval JSON schema

```json
{
  "score": <quality.overall と同値の 0-100>,
  "plan_implementation": {"overall": 100, "notes": "E2E 評価では plan との突き合わせは対象外"},
  "quality": {
    "overall": <eval-schema.json の weight による breakdown の加重平均 0-100。判定対象が 0 件なら 0>,
    "breakdown": {
      "ac_pass_rate": <判定対象行のうち pass の割合 0-100>,
      "evidence_grounding": <全 verdict に操作と観測の evidence が付いているか 0-100>
    }
  },
  "results": [
    {"ac": "AC-n", "verdict": "pass|fail|pending|skipped", "skip_reason": "<skipped のとき unit|human|unsafe|precondition。それ以外は JSON の null>", "evidence": "<行った操作と観測した内容>"}
  ],
  "side_effects": ["<評価中に対象へ残した状態の変更>"],
  "feedback": "<high → medium → low を畳み込んだ string サマリ>",
  "feedback_structured": {
    "high":   [{"ac": "AC-n", "message": "<期待結果と観測結果の差>"}],
    "medium": [{"ac": "AC-n", "kind": "spec_conflict|ambiguous", "message": "<判定できなかった理由>"}],
    "low":    [{"ac": "AC-n", "message": "<対象外にした理由>"}]
  },
  "undecidable": <bool>,
  "passed": <bool>,
  "evaluator_skill": "e2e-evaluator"
}
```

**passed の判定**: `fail` が 0 行かつ `undecidable` でなければ `passed: true`、`fail` が 1 行でもあれば score に関わらず `passed: false` とする (受け入れ基準を満たさない実装をコミットに進めないため)。`pending` は合否に影響しない — `pending` を不合格に含めると、修正すべき箇所が無いのに差し戻しループに入るためである。`pending` の行は呼び出し元がユーザーに判定を委ねる。`undecidable: true` のときは `passed: false` とし、呼び出し元は不合格ではなく判定不能として扱う。`score` は参考値であり合否には使わない。

## 採点観点の定義

| breakdown キー | 評価内容 | 根拠 |
|---------------|---------|------|
| `ac_pass_rate` | 判定対象の受け入れ基準行のうち、操作の結果が期待結果と一致した行の割合 | spec「受け入れ基準 (テストケース表)」の期待結果 |
| `evidence_grounding` | 各 verdict に、行った操作と観測した内容が記録されているか。記録の無い verdict は減点する | 手順 3 |

## Gotchas

- **コードを読んで「動くはず」と判断しない** — 本スキルの価値は、実装側と前提を共有しないことにある。操作せずに pass を付けた行は評価として無効である
- **見た目の良し悪しを判定しない** — 表示の有無や文言の一致は判定できるが、配置や色の妥当性は挙動ゲートのユーザーが判定する。評価者が判定すると、ユーザーが合意した見た目の正本を評価者が上書きすることになる
- **受け入れ基準の表にない操作を採点に加えない** — 気づいた問題は feedback に書いてよいが、`results` には表の行だけを並べる。表はユーザーとの合意の記録であり、評価者が基準を増やすと合意の外で不合格が生まれる
- **元に戻せない操作を「テストだから」と実行しない** — 対象が本番相当の環境である可能性を常に考える。判断に迷う操作は unsafe として対象外にする
- **不合格の理由を実装の推測で書かない** — 「おそらく X の処理が抜けている」ではなく「Y を入力して Z を押したところ、期待結果 P に対して Q が表示された」と書く。原因の特定は実装側の仕事であり、評価者の推測は修正を誤った方向に導く
