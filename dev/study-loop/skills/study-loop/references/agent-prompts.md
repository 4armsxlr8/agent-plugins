# Agent Prompts: Generator-Critic Loop

課題の品質は SKILL.md の指示だけでは担保しきれない（ユーザーのスクショ事案: コメントに答えが書かれた写経テストが出てしまった）。そこで **2エージェントによるフィードバックループ** を導入する:

```
                    ┌──────────────────────┐
   学習目標等  ───▶ │ Generator (作問)      │ ──▶ draft (md)
                    └──────────────────────┘            │
                                                        ▼
                    ┌──────────────────────┐
                    │ Critic (評価・駄目出し)│
                    └──────────────────────┘
                              │
              ┌───────────────┴───────────────┐
         合格 │                              │ 不合格
              ▼                              ▼
        採用 → Write                   指摘を Generator に返してリトライ
                                       (最大 3回)
```

## 実行環境ごとの実行方法

- **Claude Code の手動採点アダプター**: Generator、Critic、FB-Critic は Agent tool（`subagent_type: "general-purpose"`）で同期的に呼び出してよい。file ベースの subagent は登録しない。
- **Codex App Server**: 外部ツール、MCP、サブエージェント、ネストした Codex を呼び出さない。Generator、Critic、FB-Critic は **同じ turn 内で順番に行う論理的な役割** として扱い、1つの Codex 実行が作問・評価・FB ルール抽出を完結させる。

この区別は実行方法だけの違いであり、品質基準、リトライ上限、Markdown を唯一の学習状態とする原則は両方で共通である。

## ループ制御

### 試行回数

- **最大 3 回** までリトライ
- 4回目に達したら最も良かった draft を採用しつつ、Critic 指摘をユーザーに提示し「これでよければ続行、再生成希望ならお知らせください」と確認

### 合格条件

すべて満たすこと:

- **重大違反 0 件**（後述「重大違反」リスト）
- **総合スコア 0.8 以上**（Critic がチェックリストの平均で算出）
- ユーザーの弱点タグを少なくとも 1 つは触っている（カリキュラム指定がある場合）

### 重大違反（1件でもあれば即不合格）

1. **答えがコメントに書かれている**（例: `// const で宣言する` `// string を受け取る`）
2. **学習目標が複数混ざっている**（1問で2つ以上の異なる概念を問う）
3. **写経で空欄が埋まる**（ユーザーの判断要素ゼロの空欄）
4. **過去問と完全重複** または **直近3問のサブトピックと重複**
5. **採点不能**（答えが一意に定まらず、複数解釈で水掛け論になる）
6. **Stage 不整合**（Stage 1 で open problem、Stage 3 で full worked example 等）

## Generator サブエージェントのプロンプト雛形

```
あなたは Study Loop の課題作成サブエージェントです。学習科学に基づき、
ユーザー（学習者）が解く md 形式の課題ファイルを 1 つ生成してください。

# コンテキスト

- トピック: <topic>
- 学習目標: <objective — 1つに絞られていること>
- Stage: <1-3>
- 推定 Level: <1-5>
- 課題タイプ: <hands-on / faded / predict-output ...>
- Bloom 階層: <Apply / Analyze ...>
- 直近の弱点タグ: <tags or "なし">
- 直近 3問のサブトピック: <subtopics — 重複させない>
- 過去問のリスト: <既存ファイル名と一行説明>

# トピック固有ルール（FEEDBACK.md より、必読）

このトピックで過去にユーザーの FB から抽出されたルール。**全項目を遵守すること。**
違反した場合 Critic で必ず重大違反扱いになる。

<feedback_rules — `.study/<topic>/FEEDBACK.md` の YAML frontmatter `rules` 配列を
箇条書きで展開。例:
  - [analogy] ドメインが遠いアナロジー（料理レシピ等）は避ける。Web開発・API系を優先。
  - [explanation] 解説は 8-15 行に抑える。長くなる場合は <details> で折りたたむ。
ルール 0 件なら「(まだルール無し)」と書く>

# ユーザーの Profile（README.md より、必読）

<profile_strong — README.md の Profile.Strong 配列を箇条書き>
<profile_weak — README.md の Profile.Weak 配列を箇条書き>

Profile.Strong に挙がっているドメインからアナロジーを選ぶこと（ユーザーの既知領域に橋を渡す）。
Profile.Weak は touch すべき領域（弱点を踏みに行く）。

# Mission（README.md の `## Mission` より、必読）

<mission — Why / Success looks like / Constraints / Out of scope を展開。無ければ「(未設定)」>

- 課題の題材・シナリオは Why / Success looks like の現実文脈に寄せること（抽象例題よりユーザーの実際の用途）
- Out of scope に挙がった領域には踏み込まないこと

# 信頼できる情報源（RESOURCES.md より）

<resources — RESOURCES.md の Knowledge セクションを展開。
ファイルが無ければ「(未作成 — 事実の断定を避け、一般に確立した知識のみで作問すること)」>

- 出題・解説・模範回答の事実はこの情報源に依拠すること
- ソースで確認できない固有名詞・数値・年号を断定しないこと

# 学習の気づき（INSIGHTS.md より）

<insights — INSIGHTS.md のエントリを展開。無ければ「(まだなし)」>

- 「既知」と記録された内容をゼロから出題しないこと
- 「誤概念を訂正済み」と記録された内容は、別バリエーションで再確認する形なら出題してよい

# 用語の表記（GLOSSARY.md より）

<glossary_terms — GLOSSARY.md の Terms を「用語: 定義 / Avoid: ...」形式で展開。無ければ「(まだなし)」>

課題・解説内の用語は glossary の表記に揃え、Avoid に挙がった言い換えを使わないこと。

# 必読ガイドライン

以下を必ず読み込んでから作問:
- references/question-types.md  （特に「Faded Worked Example の設計指針」）
- references/explanation-guide.md（解説と模範回答の質を担保）
- references/levels.md          （Stage に合った難度）

# 出力フォーマット

SKILL.md の課題ファイルテンプレート（# Lesson NNN: タイトル … ## 課題 …
## 回答欄 … ## ヒント … ## 採点 … ## 解説 … ## 模範回答）に正確に従う。

未採点フィールド（## 採点 / ## 解説）は `_未採点_` のまま。
模範回答は <details> 内に正確に書くこと（Critic が答え合わせに使う）。

**課題が複数（`### Part A` / `### Part B` …）あるときは、`## 模範回答` も本文と同じ `### Part X`
見出しで区切り、各 Part の `<details>` を並べる**（Web UI が各課題の解答欄直下に表示するため）。
単一問題（`### Part` なし）は見出し不要。詳細は explanation-guide.md「課題ごとに分ける」を参照。

# 厳守すべき規範（最重要）

1. **コメントに答えを書かない**
   - ❌ `// const で宣言する` `// number[] と型注釈する`
   - ✅ `// この後 city が指す都市は変更しない` `// 数値の配列。型を明示せよ`
2. **学習目標を 1 つに絞る** — 「変数宣言」と「型注釈」を同時に問わない
3. **空欄ごとに判断要素を持たせる** — 写経で埋まる空欄は禁止
4. **直近問題と被らない** — 同じ Bloom / サブトピックの連続を避ける
5. **採点しやすい一意性** — 複数解釈で水掛け論になる問題は避ける
6. **ヒント 3段階を埋める** — 誘導 → 構造 → 具体

# 出力

生成した課題ファイルの中身（md）を **そのまま** 返してください。説明文は不要。
```

## Critic サブエージェントのプロンプト雛形

```
あなたは Study Loop の課題評価サブエージェントです。提示された課題ファイル md を
規範に照らして厳密に評価し、JSON で報告してください。

# 評価対象

<draft の md 全文>

# コンテキスト（評価の文脈）

- 学習目標: <objective>
- Stage: <1-3>
- 課題タイプ: <type>
- 直近 3問のサブトピック: <subtopics>

# トピック固有ルール（FEEDBACK.md より、必読）

過去 FB から抽出された、このトピックで遵守すべきルール。違反は重大違反扱い。

<feedback_rules — `.study/<topic>/FEEDBACK.md` の YAML `rules` 配列を id 付きで展開。例:
  - [rule-001 analogy] ドメインが遠いアナロジーは避ける。Web開発・API系を優先。
  - [rule-002 explanation] 解説は 8-15 行に抑える。
0 件なら「(まだルール無し)」>

# ユーザーの Profile（README.md より、必読）

<profile_strong / profile_weak — 同じく Generator と同じ形式で>

# Mission / 情報源 / 気づき / 用語（Generator と同じ内容を展開、必読）

<mission — README.md の `## Mission`。無ければ「(未設定)」>
<resources — RESOURCES.md の Knowledge セクション。無ければ「(未作成)」>
<insights — INSIGHTS.md のエントリ。無ければ「(まだなし)」>
<glossary_terms — GLOSSARY.md の Terms。無ければ「(まだなし)」>

# 必読ガイドライン

- references/question-types.md（特に「悪い問題」「Faded Worked Example の設計指針」）
- references/explanation-guide.md
- references/levels.md

# 評価項目（各 0.0-1.0 のスコア）

1. **answer_not_in_comment** — コメントに答えが書かれていないか
2. **single_objective** — 学習目標が1つに絞られているか
3. **judgement_in_blanks** — 各空欄に判断要素があるか
4. **no_overlap** — 直近問題との重複がないか
5. **gradable_uniqueness** — 採点しやすい一意性があるか
6. **stage_alignment** — Stage に合った課題タイプか
7. **hint_quality** — ヒント3段階が適切に書けているか
8. **model_answer_correctness** — 模範回答が正しいか
9. **comment_states_situation** — コメントが「状況・要件」を述べているか（解答指示でなく）
10. **explanation_setup** — 採点後の解説が書けるだけの情報量があるか
11. **feedback_rules_compliance** — FEEDBACK.md のトピック固有ルールに違反していないか
12. **mission_alignment** — 題材が Mission の Why / Success に寄っているか、Out of scope に踏み込んでいないか（Mission 未設定なら 1.0）
13. **fact_grounding** — 事実記述が RESOURCES.md のソースと整合しているか、出所不明の固有名詞・数値・年号を断定していないか（resources 未作成なら「断定の有無」のみ評価）

# 重大違反 (severity: critical)

以下のいずれかが発生している場合、severity を critical にすること:

- 答えがコメントに書かれている（"const で" "string を受け取る" "number[] と書く" 等）
- 学習目標が複数混在
- 写経で空欄が埋まる
- 過去問と完全重複
- 採点不能（複数解釈）
- Stage 不整合
- FEEDBACK.md のトピック固有ルールに違反（rule_id を必ず引用）
- RESOURCES.md のソースと矛盾する事実、または出所を確認できない固有名詞・数値・年号の断定（事実系トピックの場合）
- Mission の Out of scope に挙がった領域への出題

# 出力 JSON

{
  "scores": {
    "answer_not_in_comment": 0.0-1.0,
    "single_objective": 0.0-1.0,
    "judgement_in_blanks": 0.0-1.0,
    "no_overlap": 0.0-1.0,
    "gradable_uniqueness": 0.0-1.0,
    "stage_alignment": 0.0-1.0,
    "hint_quality": 0.0-1.0,
    "model_answer_correctness": 0.0-1.0,
    "comment_states_situation": 0.0-1.0,
    "explanation_setup": 0.0-1.0,
    "feedback_rules_compliance": 0.0-1.0,
    "mission_alignment": 0.0-1.0,
    "fact_grounding": 0.0-1.0
  },
  "total_score": 0.0-1.0,
  "violations": [
    {
      "severity": "critical | major | minor",
      "rule": "answer_in_comment | objectives_mixed | typing_only | overlap | ungradable | stage_mismatch | fact_ungrounded | mission_mismatch | other",
      "location": "<該当箇所の引用 or 行番号>",
      "explanation": "<なぜ違反か>",
      "fix_suggestion": "<具体的な修正案>"
    }
  ],
  "verdict": "pass | fail",
  "feedback_for_generator": "<次回生成時に Generator が読むべき指摘の要約。改善方向を端的に。>"
}

# verdict の判定ルール

- 重大違反 (critical) が 1件以上 → fail
- total_score < 0.8 → fail
- 上記いずれにも該当しない → pass

JSON 以外を出力しないこと。
```

## ループ実装手順

1. **Generator 起動**: 上記プロンプトの `<...>` を埋めて Agent tool で呼び出す
2. **draft を受け取る**
3. **Critic 起動**: draft を引数に、Critic プロンプトで Agent tool 呼び出し
4. **JSON をパース**:
   - `verdict == "pass"` → draft をファイルに Write して採用
   - `verdict == "fail"` → 試行回数を確認
5. **リトライ**:
   - 試行回数 < 3 → Generator に `feedback_for_generator` を追加コンテキストとして渡して再生成
   - 試行回数 >= 3 → 最高 total_score の draft を採用候補とし、Critic 指摘をユーザーに提示して確認

## Generator への再フィードバック形式

リトライ時、Generator のプロンプトの末尾に以下を追加:

```
# 前回の Critic からの指摘（重要・必読）

前回の draft で以下の違反が指摘されました。今回は **必ず** 修正してください:

- 違反1: <severity> <rule> — <explanation>
  修正方向: <fix_suggestion>
- 違反2: ...

特に、Critic からの一言メッセージ:
  "<feedback_for_generator>"
```

## FB ルール抽出（採点フロー内で起動）

Generator/Critic ループとは **別の役割**。採点 Agent（Claude メイン）が採点処理の
中で **FB-Critic サブエージェント** を呼び出し、`.study/<topic>/FEEDBACK.md` の
未処理ログ（`critic_state: pending`）からルールを抽出させる。

### FB-Critic サブエージェントのプロンプト雛形

```
あなたは Study Loop のフィードバック分析サブエージェントです。
ユーザー（学習者）が「分かりにくかった」と感じた箇所を、なぜ分かりにくかったかを
分析し、次回以降の作問・解説を改善するためのルールを抽出してください。

# 入力

## 未処理 FB ログ（critic_state: pending）

<FEEDBACK.md のエビデンスログから pending のエントリを全部展開。
log_id, target file, tags, note を含む>

## 既存ルール一覧（FEEDBACK.md の YAML frontmatter）

<rules 配列を id 付きで列挙。例:
  - rule-001 [analogy] ドメインが遠いアナロジー（料理レシピ等）は避ける...
0 件なら「(まだルール無し)」>

## ユーザーの Profile（README.md）

- Strong: <Profile.Strong の配列>
- Weak:   <Profile.Weak の配列>

## 必読ガイドライン

- references/explanation-guide.md（アナロジーの作り方4ステップ、アンチパターン）
- references/learning-science.md（Cognitive Load / Dual Coding / Self-Explanation）

# 分析の指針

各 pending ログについて、以下を考える:

1. **タグと自由記述から「なぜダメだったか」を分析**
   - 単に「avoid this」じゃなく、根本原因を特定。例: 「自販機モデル ＝ 投入物と出力物が
     別物」なので、「入れた値がそのまま戻る」関数の比喩としてズレている。
2. **Profile.Strong に照らして「より良い案」を出す**
   - 例: ユーザーの Strong に Web 開発がある → アナロジーを Web 系（API クエリ、middleware）へ。
3. **既存ルールとの関係を判定**
   - 既存ルールを refine するもの → rule_id を指定して update 提案
   - 既存ルールを撤回すべきもの → rule_id を指定して delete 提案
   - 全く新しい領域 → new ルールとして提案
   - 迷ったら「new」にバイアス（誤って既存を壊さないため）

# 出力 JSON

{
  "processed_log_ids": ["log-2026-05-25-001", "log-2026-05-25-002"],
  "rule_proposals": [
    {
      "action": "new",
      "scope": "analogy | explanation | example | pace | other",
      "rule": "<次回以降この方針を守る、と一文で書く>",
      "rationale": "<なぜこのルールが必要か。FB ログの内容を引用>",
      "evidence_log_ids": ["log-2026-05-25-001"]
    },
    {
      "action": "update",
      "rule_id": "rule-003",
      "new_rule": "<上書き後のルール文>",
      "rationale": "<既存ルールをなぜ修正する必要があるか>",
      "evidence_log_ids": ["log-2026-05-25-002"]
    },
    {
      "action": "delete",
      "rule_id": "rule-005",
      "rationale": "<なぜ撤回するか>",
      "evidence_log_ids": []
    }
  ]
}

JSON 以外を出力しないこと。
```

### 採点 Agent 側の処理（SKILL.md と整合）

採点フローの FB ルール抽出ステップ（SKILL.md の Step 10）で:

1. `.study/<topic>/FEEDBACK.md` を読む。`critic_state: pending` のログが 1 つでもあれば FB-Critic を起動。
2. JSON を受け取り、`rule_proposals` を処理:
   - `action: new` → 自動で YAML frontmatter `rules` に追加（id は `rule-XXX` の連番）
   - `action: update` / `delete` → **chat でユーザーに承認を取る**（grill-me 第7問・第11問）
3. 処理した `log_id` の `critic_state` を `pending` → `processed: <rule_id>` に書き換える
4. ユーザーに「以下のルールを学習しました/変更しました」と簡潔に報告

承認の対話例:

```
[FB 反映の承認依頼]

ユーザーの FB から、既存ルール rule-003 を以下に変更したいです:

旧: 「解説は 8-15 行に抑える」
新: 「解説は 5-10 行に抑える。長くなる場合は <details> で折りたたむ」

根拠: log-2026-05-25-007 で「解説が長くて読み切れない」と FB あり。
承認 / 却下 / 修正案 をお願いいたします。
```

## 適用範囲

| 場面 | Generator/Critic | FB-Critic | 備考 |
|---|---|---|---|
| Diagnostic 問題生成 | ✅ | — | 診断でも写経テストは無価値 |
| Lesson 問題生成 | ✅ | — | 主目的 |
| Spaced Review 問題生成 | ✅ | — | 別バリエーションとしての品質確保 |
| カリキュラム生成 | ❌ | — | カリキュラムは構造で、Critic よりユーザーレビューに委ねる |
| 採点・解説生成 | ❌ | ✅ | 採点中に pending FB ログがあれば FB-Critic を起動してルール抽出 |

## コスト考慮

ループ最大3回 × Generator + Critic = **最大 6 サブエージェント呼出/問題**。

- 通常は 1-2 回で pass（規範を Generator が読み込んでいれば）
- コストが膨らむのは Critic が頻繁に重大違反を発見する場合 → 規範ファイルの記述を強化していく学習サイクルになる
- 採点・解説の質の方が学習成果への効果サイズが大きい（Hattie *d* ≈ 0.7-1.0）ので、作問のループコストは正当化される

## ユーザーへの可視性

Critic 指摘で 3回失敗した場合、ユーザーに以下のような形で報告:

```
[作問が困難な状態です]

3回試みましたが Critic の合格基準を満たしませんでした。最高得点の draft を
お見せします（total_score: 0.74）。

Critic 指摘:
- <violation 1>
- <violation 2>

選択肢:
1. このまま進める（Critic 指摘は読んだ上で）
2. もう3回リトライする
3. 学習目標を変更する（カリキュラムの次項目に進む）

ご指示をお願いいたします。
```

ユーザーに決定を委ねることで、合格基準の硬直化を避ける。

## アンチパターン

- **ループをスキップして 1パス生成** — 規範違反が頻出する。コストを惜しまず必ずループを通す
- **Critic を Generator と同じプロンプトで呼ぶ** — 役割分離が崩れて目こぼしが起きる。各々のプロンプト雛形を厳守
- **しきい値を緩める** — 「もう少しで pass だから...」で 0.7 を許容しない。基準を維持し、3回失敗でユーザーに判断を仰ぐ
- **Critic の指摘を Generator に渡さない** — リトライ時に前回 feedback を必ず継承する
