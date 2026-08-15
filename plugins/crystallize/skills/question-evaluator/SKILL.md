---
name: question-evaluator
description: 「質問監査」「質問レビュー」で発動。ユーザーに出す質問の前提と二択の正当性を採点する evaluator
user-invocable: true
argument-hint: "<context-json path | 質問ファイル path | 質問の生テキスト>"
context: fork
agent: general-purpose
metadata:
  purpose: judge
  trigger: both
  shape: forked
  role: evaluator
---

# question-evaluator

インタビュー系スキル (find-unknowns 等) がユーザーに出す質問を、出題側とは独立したコンテキストで監査する評価者。質問は出題側の仮実装案の分岐点から生成されるため、案に含まれた思い込み (誤った前提・偽の二択・誘導) をそのまま引き継ぐ — それを出題前に検出する。

- **質問・呼び出し元スキル・評価基準を修正しない (Read のみ)** — 評価をパスする最短経路として基準側を書き換える誘惑を構造的に断つ (評価基準の保護原則)
- **呼び出し元の実装案・ledger・設計文書は、渡されても読まない** — 案を見た監査者は同じバイアスに迎合する。コードベース本体の探索は前提の事実確認のためにむしろ必須
- **model は frontmatter で指定しない (= セッションモデルを継承)** — 評価者は出題側と同格以上に保つ。質問の作り直しは安いが、監査の見逃しは実装後に発覚して高くつく

## 契約 (単一)

- **Input**: `$ARGUMENTS` = context JSON ファイルのパス (evaluator 単一契約)。JSON キーは `project_dir` / `plan` / `criteria` / `threshold` / `turns_dir` / `iteration` / `output_contract` (`eval_file` / `schema` / `instructions`)。監査対象の質問ファイルは `plan` で指定する
- **Output**: `output_contract.eval_file` に下記 eval JSON schema で Write する

### 質問ファイルの形式 (呼び出し元が用意する)

```markdown
- タスク: <一行要約>
- 質問: <質問文。前提の開示込み>
- 選択肢: <AskUserQuestion に渡す予定の options。なければ省略>
```

### context JSON 不在時のフォールバック

`$ARGUMENTS` が context JSON として解釈できない場合 (JSON でない / ファイル不在 / `output_contract` が空):

- ファイルパスなら質問ファイルとして Read、それ以外は質問の生テキストとして扱う
- タスク一行要約が無ければその旨を feedback に明記し、質問文単体で評価する (前提の事実確認の精度は落ちる)
- eval JSON の書き出し先は `{project_dir=カレントディレクトリ}/output/eval-<YYYYMMDD-HHMMSS>-question-evaluator.json` (ディレクトリが無ければ作成)
- Markdown フィードバックは stdout に出し、末尾に同 schema の eval JSON を添付

## 手順

### 1. 前提の抽出と分類

質問文から前提をすべて列挙し、2 種に分類する。

- **検証可能**: コードベース・ドキュメントで真偽が決まる主張 (「A と B は両立しない」「既存の認証は X 方式」等)
- **好み・優先順位**: ユーザーにしか決められないこと

### 2. 検証可能な前提の事実確認

検証可能な前提は、確からしく見えても必ず裏取りする — コードベースで検証できるものは Grep / Read / Explore subagent、API 仕様・ライブラリの機能有無・プラットフォーム制約など一般技術知識に属するものは WebSearch / WebFetch / 公式ドキュメントで。LLM は知識境界を正確に把握できず、もっともらしい誤前提を高い確信度で保持するため。

二択・優先度型の質問 (「A と B どちらを優先しますか」) は、**両立案を最低 1 つ自力で構成してみる**。無理なく構成できたら偽の二択と確定する。

### 3. 誘導と選択肢のチェック

- 特定の答えへ誘導する表現・推奨の埋め込みがないか
- 前提が質問文中に開示されているか (ユーザーが選択肢ではなく前提側を撃てるか)
- 選択肢リストが答えの空間を狭めていないか (両立案の欠落、自然な選択肢が「その他」に押し込まれる構成)

### 4. フィードバックと eval JSON

Markdown フィードバック (前提の検証結果表 / 二択の正当性 / 誘導・選択肢 / 総評) を出し、eval JSON を書き出す。`passed: false` の場合は必ず `rewrite` に書き直し案 (質問文 + 選択肢) を入れる。

## eval JSON schema

```json
{
  "score": <quality.overall と同値の 0-100>,
  "plan_implementation": {"overall": 100, "notes": "質問監査では実装計画との突き合わせは対象外"},
  "quality": {
    "overall": <0-100>,
    "breakdown": {
      "premise_grounding": <0-100>,
      "dilemma_validity": <0-100>,
      "neutrality": <0-100>,
      "option_coverage": <0-100>
    }
  },
  "feedback": "<high → medium → low を畳み込んだ string サマリ>",
  "feedback_structured": {
    "high":   [{"area": "<premise|dilemma|neutrality|options>", "message": "<指摘 + 根拠 (裏取りしたファイル:行)>"}],
    "medium": [{"area": "...", "message": "..."}],
    "low":    [{"area": "...", "message": "..."}]
  },
  "rewrite": "<書き直した質問文 + 選択肢。passed: true なら null>",
  "passed": <bool>,
  "evaluator_skill": "question-evaluator"
}
```

**passed の判定**: 検証可能な前提に誤りが 1 つでも確認されたら、score に関わらず `passed: false` (誤前提の質問はどれだけ丁寧に書かれていても出してはいけない)。それ以外は score >= threshold (context JSON 指定。フォールバック時は 80)。

## 採点観点の定義

基準の正本は `find-unknowns` SKILL.md「質問の関所」の 3 規則。同節が改訂されたら本表と `eval-schema.json` を追随させる。

| breakdown キー | 評価内容 | 根拠 |
|---------------|---------|------|
| `premise_grounding` | 検証可能な前提が事実 (コードベース、または一般技術知識なら Web / 公式ドキュメント) と一致するか。裏取りせず確信だけで通した前提があれば減点 | 質問の関所 規則 1 (前提の裏取り) |
| `dilemma_validity` | 二択・優先度質問で両立不能のメカニズムが成立しているか。両立案が構成できたら大幅減点 | 質問の関所 規則 2 (二択の証明義務) |
| `neutrality` | 誘導表現がなく、前提が質問文中に開示されているか | 質問の関所 規則 3 (前提の開示) |
| `option_coverage` | 選択肢が答えの空間を歪めていないか (両立案の欠落等)。選択肢なしの質問は N/A (満点扱い) | 質問の関所 監査項目 (選択肢による答えの狭め) |

## Gotchas

- **「前提は正しそう」で裏取りを省略しない** — 監査の存在意義は出題側の確信を疑うことにある。出題側と同じ確信で通すなら監査は無意味
- **書き直し案で新しい前提を持ち込まない** — rewrite に自分の未検証前提を混ぜると監査が新たなバイアス源になる。書き直しは検証済みの事実と開示された前提だけで構成する
