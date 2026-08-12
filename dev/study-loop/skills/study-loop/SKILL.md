---
name: study-loop
description: "任意トピック（プログラミング・語学・数学・歴史・資格試験など何でも）について、エビデンスベース学習科学（Hattie のフィードバック理論、Roediger の retrieval practice、Cepeda の spacing、Sweller の worked example、Bjork の desirable difficulties、Bisra の self-explanation 等のメタ分析）に基づくカリキュラムを自動生成し、課題ファイル形式（問題用紙 + 回答欄）で対話的に学習を進める勉強用スキル。勉強したい、問題を出してほしい、体系的に学びたい、採点してほしいという意図で使う。単に解説せず、課題を生成し、回答記入、採点、解説のループへ進める。"
---

# Study Loop — 学習ループ

## Overview

任意トピックの段階的学習を支援するスキル。**エビデンスベース** の設計を貫く（学習効率の研究結果を実装に反映）。トピック非依存（プログラミング・語学・数学・歴史・資格試験...）。

ユーザーが「○○を勉強したい」「カリキュラム作って」と言ったら、単に解説を垂れ流すのではなく、**課題ファイルを md で生成 → ユーザーが回答記入 → LLM が読んで採点・解説** のループに切り替える。

## 設計の根拠

すべての判断はメタ分析・システマティックレビューに基づく。詳細は `references/learning-science.md`。

| 原則 | 効果サイズ | 実装場所 |
|---|---|---|
| Feedback の質（Hattie） | *d* ≈ 0.7-1.0 | 採点後の Feed-up / Feed-back / Feed-forward 必須 |
| Retrieval Practice（Roediger） | *d* ≈ 0.5-0.8 | 出題は recall 中心、recognition は補助 |
| Self-Explanation（Bisra） | *g* ≈ 0.55 | 採点前に「なぜそう答えた？」を必ず挟む |
| Worked Examples + Faded（Sweller） | *d* ≈ 0.5-1.0 | Stage 別に full → faded → open |
| Distributed Practice（Cepeda） | *d* ≈ 0.4-0.9 | 目標保持期間の 10-15% で復習配置 |
| Interleaving（Brunmair） | *g* ≈ 0.42 | 単元理解後に複数単元混在 |
| Elaborative Interrogation | *d* ≈ 0.42 | Stage 2 以降で "Why?" 混入 |

## ディレクトリ構造

セッションは **cwd 配下** に作成（sandbox の `.` allow に対応）:

```
.study/<topic-slug>/
├── README.md                       # 進捗ダッシュボード（Profile.Strong/Weak の静的記録、## Mission を含む）
├── curriculum.md                   # 学習ロードマップ
├── FEEDBACK.md                     # ユーザーの FB から抽出したトピック固有ルール（動的に成長）
├── RESOURCES.md                    # 厳選した信頼できる情報源（パラメトリック知識を信用しない）
├── GLOSSARY.md                     # 用語集 — ユーザーが「正しく使えた」用語だけを載せる圧縮知識
├── INSIGHTS.md                     # 非自明な気づきのログ（ADR の学習版、Generator/Critic が必読）
├── diagnostic/                     # 診断フェーズ専用
│   ├── 01-<slug>.md
│   ├── 02-<slug>.md
│   ├── 03-<slug>.md
│   ├── 04-<slug>.md
│   └── summary.md                  # 診断結果
└── lessons/                        # 通常学習
    ├── 001-<slug>.md
    ├── 002-<slug>.md
    └── ...
```

`<topic-slug>` の作り方: 小文字化 → 空白を `-` に → 記号除去（例: `TypeScript Generics` → `typescript-generics`）。

学習履歴を git 管理するか `.gitignore` で除外するかはユーザーの好み。

## 起動と実行環境アダプター

どの実行環境でも、以下の意図を同じ成果に結び付ける。実行環境固有のコマンド名は、対応するアダプターがある場合だけ補助的に解釈する。

| 入力 | 動作 |
|---|---|
| トピックを指定して学習を始める | セッション開始（既存なら読み込み、なければ新規作成 → 診断 → カリキュラム生成） |
| セッション一覧を求める | `.study/` を走査し、既存セッション一覧を表示 |
| 自然言語の回答 | 直前の lesson への回答として採点プロトコルへ |
| `採点して` / `次へ` | 直近の課題ファイルを読み込み、採点、解説、次 lesson 生成を行う |
| `ヒント` | 段階ヒントを提示（採点には影響しない） |
| `わからない` / `わかりません` / 空欄 | **必須プロトコル**（後述）に従って模範回答 + 解説を提示 |
| 進捗を求める | `README.md` から進捗ダッシュボードを表示 |
| 復習を求める | Spaced Review を実行し、過去 lesson の別バリエーションを出題 |
| 終了を求める | セッションを終了し、最終サマリを `README.md` に追記 |

### 任意のコマンドアダプター

コマンドを持つ実行環境では、`/study-loop <topic>`、`/study-loop status`、`/study-loop review`、`/study-loop end`、`/study-loop list` を上の各意図に対応付けてよい。コマンドがない環境でも自然言語だけで同じ手順を実行する。

## Loop overview

```
[start]
  ↓
Phase 0: Setup
  - Topic / Goal / 目標保持期間 / 目標 Level / 時間予算 をユーザーに確認
  - README.md と curriculum.md の枠を作成して保存
  ↓
Phase 1: Diagnostic（初回のみ）
  - diagnostic/01-04.md を順次生成（worked example で出題）
  - 1問ずつユーザー提示 → 回答記入 → 採点 + 必須解説 → 次へ
  - diagnostic/summary.md に結果記録
  ↓
Phase 2: Curriculum Generation
  - 診断結果から Stage 配分を決定
  - curriculum.md に Stage 別 lesson リストと Spaced Reviews を保存
  - ユーザーレビュー → 合意
  ↓
Phase 3: Lesson Loop
  - curriculum.md の次未完了 lesson に対応する課題ファイルを生成
  - ユーザーが回答欄に記入 → 「採点して」
  - 採点プロトコル実行
    1. Self-explanation を引き出す（Stage 2 以降）
    2. 3軸ルーブリック採点（rubric.md）
    3. 3層フィードバック + 解説 + 模範回答（explanation-guide.md）
  - curriculum.md のチェックを更新
  - 直近 5問の正答率で Level / Stage 調整（levels.md）
  - 必要に応じて curriculum.md に Spaced Review を追加
  ↓
Phase 4: 終了
  - 終了要求を受けたら README.md に最終サマリ
```

## Phase 0: Setup

新規セッション作成時、ユーザーから以下を引き出す（簡潔に）:

1. **Mission（なぜ学ぶか）**: 「○○ができるようになって △△ したい」という **現実の具体的な目標** を聞き出す。曖昧なら遠慮なく聞き返す（"Push back on vagueness"）。以下の4点に整理:
   - **Why**: スキル習得で現実の何が変わるか（抽象論は不可。「10月までにハーフマラソン完走」級の具体性）
   - **Success looks like**: 観察可能な達成条件を箇条書きで 2-4 個
   - **Constraints**: 時間・環境・学習スタイルの制約
   - **Out of scope**: 今回は踏み込まない隣接トピック（カリキュラム膨張の防止弁）
2. **トピック粒度の確認**: 「TypeScript」のような広いトピックは「Generics に絞る」「型推論に絞る」など狭い粒度を提案
3. **目標保持期間**: 「いつまでこの状態でいたいか」（試験前1週間 / プロジェクト1ヶ月 / キャリア半年〜）
4. **目標 Level**: 1-5 のどこを目指すか（LLM が「このトピックなら Level 4 を提案」と推奨しユーザーが同意）
5. **時間予算**: 「1日 30分 × 2週間」など

これらを `README.md` のヘッダーと `## Mission` セクションに記録。Mission は **1画面以内** に収める（超えたら計画に変質している）。学習途中で目標が変わったら Mission を更新し、古い記述を残さない。Mission の運用ルール詳細は `references/knowledge-assets.md`。

### README.md のテンプレート

```markdown
# Study Loop: <topic>

**Started**: <YYYY-MM-DD>
**Last updated**: <YYYY-MM-DD>
**Format**: interactive  <!-- or "set" -->
**Target Level**: 4
**Current Level**: -  <!-- 診断後に埋める -->
**Confidence**: -
**Retention Interval**: 1ヶ月  <!-- 目標保持期間 -->
**Time Budget**: 1日 30分 × 14日
**Stage**: -  <!-- Foundation / Practical / Design -->
**Diagnostic complete**: false
**Ended**: -

## Mission

### Why

<スキル習得で現実の何が変わるか。具体的に 1-2 行>

### Success looks like

- <観察可能な達成条件>
- <観察可能な達成条件>

### Constraints

- <時間・環境・学習スタイルの制約>

### Out of scope

- <今回は踏み込まない隣接トピック>

## Profile

### Strong
- (まだなし)

### Weak
- (まだなし)

## Progress

- Stage 1 (Foundation): 0 / N
- Stage 2 (Practical):  0 / N
- Stage 3 (Design):     0 / N

## Recent scores

(空、最新5問のスコアをここに溜める)
```

### curriculum.md のテンプレート

`Phase 2` で診断後に作成する。テンプレート定義は `references/curriculum-design.md` 参照。

## Phase 1: Diagnostic

`README.md` の `Diagnostic complete: false` の場合のみ実施。**通常学習と分離** することが重要（ユーザーのフィードバック反映）。

### 診断問題の作成

Bloom 階層の異なる **4問** を `diagnostic/<NN>-<slug>.md` として順次生成:

1. **Remember 寄り** (Level 1-2 判定)
2. **Apply 寄り** (Level 2-3 判定)
3. **Analyze 寄り** (Level 3-4 判定)
4. **Evaluate / Create 寄り** (Level 4-5 判定)

各問題は **Generator-Critic ループ** を必ず経由する（`references/agent-prompts.md`）。1パス生成は写経テスト等の規範違反が頻出するため禁止。診断問題でも品質基準は通常 lesson と同じく重大違反 0 件・total_score 0.8 以上。

### 課題ファイル（共通テンプレート）

診断問題と通常 lesson の両方で同じ md テンプレートを使う:

```markdown
# {Diagnostic / Lesson} {N}: <title>
Level <1-5> / <bloom> / <type> / Stage <0-3>

<!-- diagnostic は Stage 0、lesson は Stage 1-3 -->

## 学習目標

- <1-2 行>

## 課題

<問題文。前提と問いを分けて 1スクリーンに収める>

## 回答欄

<!-- ここに記入してください。書き終わったら「採点して」と伝えてください -->



## ヒント

<details><summary>ヒント1: 着眼点</summary>...</details>

<details><summary>ヒント2: 構造</summary>...</details>

<details><summary>ヒント3: 具体</summary>...</details>

---

## 採点

_未採点_

## 解説

_未採点_

## 模範回答

<details><summary>模範回答を展開して見る</summary>

...

</details>
```

**課題ごとの解説・模範回答（重要）**: 課題本文に `### Part A` / `### Part B` … と複数の課題がある lesson では、`## 解説` と `## 模範回答` も **本文と同じ `### Part X` 見出しで区切る**。Web UI がこの見出しを手がかりに、各課題の解答欄の直下へ解説・模範回答を表示する（解答欄と同じく課題ごとに並ぶ）。見出しのラベルは本文と揃える（`### Part A` で可。コロン以降の説明は無視されるので `### Part A: Faded Example` でも一致する）。複数課題のときの形:

```markdown
## 解説

### Part A

**この問題のねらい**: …
**差分の説明**: …
**次に意識してほしいこと**: …

### Part B

…

## 模範回答

### Part A

<details><summary>模範回答を展開して見る</summary>

…

</details>

### Part B

<details><summary>模範回答を展開して見る</summary>

…

</details>
```

`### Part` が1つも無い単一問題（診断問題など）は見出し不要 — `## 解説` / `## 模範回答` 直下に普通に書けば、その唯一の課題に紐付く。`### Part X` に紐付かない総評は `## 採点` に書く（全体スコア＋総評として上部・下部にまとまる）。

### 診断中の必須プロトコル

ユーザーが「わからない」「空欄」で投了した場合も、**必ず以下を実行**:

1. 採点（最低スコア 0.1-0.3）
2. 模範回答を提示
3. 解説（例え話付き、`references/explanation-guide.md`）
4. 「これは難度の高い問題でした、Level X 相当でした」と難度文脈を添える
5. 次の診断問題へ

### diagnostic/summary.md の生成

4問完了後:

```markdown
# Diagnostic Summary: <topic>

**Date**: <YYYY-MM-DD>
**Estimated Level**: <1-5>
**Confidence**: <0.0-1.0>

## Question Results

| Q | Level 判定 | Score | Bloom | 結果 |
|---|---|---|---|---|
| 1 | 1-2 | 0.X | Remember | ○ / △ / × |
| 2 | 2-3 | 0.X | Apply | ... |
| 3 | 3-4 | 0.X | Analyze | ... |
| 4 | 4-5 | 0.X | Evaluate | ... |

## Strong (現時点)
- <tag>: <根拠の問題番号>

## Weak (現時点)
- <tag>: <根拠の問題番号>

## 推奨スタート Stage
<Foundation / Practical / Design>

## 注意点

<診断から見えた特徴的な傾向>
```

ユーザーにレビューしてもらってから Phase 2 へ。「もっと易しいレベルから始めたい」「この弱点は気にしないで先に進みたい」などの調整に応じる。

## Phase 2: Curriculum Generation

詳細は `references/curriculum-design.md`。要点:

1. **リソース選定（RESOURCES.md の作成）**: カリキュラムを書く前に現在の一次資料、公式資料、査読済み資料を調査して **信頼できる情報源を 5本前後に厳選** し、`RESOURCES.md` に保存する（"Never trust parametric knowledge" — モデルの記憶だけで事実系トピックを教えない）。各リソースに「何に使うか」の1行注釈を付ける。良い資料が見つからない領域は Gaps として明記。詳細は `references/knowledge-assets.md`
2. 診断 Level + 目標 Level の差から **Stage 配分** を決定
3. 各 Stage に **lesson** を並べる（1 lesson = 30-60分粒度）
4. **Spaced Reviews** を目標保持期間の 10-15% で配置
5. **Stage 別の課題タイプ** を適切に配分（worked-full → faded → open）
6. `curriculum.md` を保存
7. ユーザーにレビューしてもらい（RESOURCES.md も見せる）、合意を得てから Phase 3 へ

## Phase 3: Lesson Loop

### lesson ファイルの生成（Generator-Critic ループ）

`curriculum.md` の次の未完了項目から学習目標を1つ決定し、**Generator-Critic ループ** で課題を生成して `lessons/<NNN>-<slug>.md` に保存する。

#### Step A: コンテキスト準備

選択ロジック（`references/curriculum-design.md` 参照）:
- 現 Stage に応じた課題タイプ（Stage 1 なら worked-full、Stage 2 なら faded、Stage 3 なら open）
- 弱点タグがあれば 3-4問に1回その領域を出題
- 直近 3問と Bloom / サブトピックを被らせない
- 単元導入直後は blocked、単元理解後は interleaved

Generator / Critic に渡すコンテキストとして以下も読み込む（存在するもののみ）:
- `README.md` の `## Mission` — 課題の題材を Why / Success に寄せ、Out of scope に踏み込まないため
- `RESOURCES.md` — 出題・解説の事実をソースに依拠させるため
- `INSIGHTS.md` — 既知と記録済みの内容の再出題や、訂正済み誤概念の放置を防ぐため
- `GLOSSARY.md` — 用語の表記をユーザーと合意済みのものに揃えるため

#### Step B: Generator の分離実行

`references/agent-prompts.md` の **Generator プロンプト雛形** を、主実行とは分離した実行コンテキストに渡す。draft（md 全文）を受け取る。

#### Step C: Critic の分離実行

draft を入力に、`references/agent-prompts.md` の **Critic プロンプト雛形** を別の分離実行コンテキストへ渡す。JSON で評価結果を受け取る。

#### Step D: 判定

- `verdict == "pass"` → draft をファイルに保存して採用、Step E に進む
- `verdict == "fail"`:
  - 試行回数 < 3 → Critic の `feedback_for_generator` を Generator に追加コンテキストとして渡し、Step B に戻る
  - 試行回数 >= 3 → 最高 total_score の draft を採用候補とし、Critic 指摘をユーザーに提示して判断を仰ぐ（採用 / 再試行 / 学習目標変更の3択）

#### Step E: ユーザーに課題を提示

採用された lesson ファイルへのパスをユーザーに伝え、Web UI 起動中なら URL を、UI 未起動なら md ファイルを開くよう案内。

詳細なエージェント仕様・プロンプト雛形・コスト・アンチパターンは `references/agent-prompts.md` 参照。

### 採点プロトコル

ユーザーが回答欄に記入 → 「採点して」または「次へ」と発話 → 以下を実行:

#### Step 1: 課題ファイルを読み込む

回答欄の内容を抽出。

#### Step 2: 「わからない」「空欄」判定

回答が:
- 完全空欄
- 「わかりません」「わからない」「？」「skip」
- 明らかな当てずっぽう（質問と無関係）

であれば → **「わからない」必須プロトコル** に分岐:

1. 責めない、否定しない
2. 採点を 0.1-0.3 で記録
3. **アナロジー → 段階ヒント or 模範回答 + 解説（例え話付き）** を必ず提示
4. Weak タグに登録 + curriculum.md に「同概念の別バリエーション」を追加
5. ユーザーに「もう一度別バリエーションで試したい？それとも次に進む？」と尋ねる

#### Step 3: Self-Explanation 引出し（Stage 2+）

採点前にユーザーに:

```
ありがとうございます。採点する前に1つだけ:
この答えに至った理由を一言で説明していただけますか？（思いつかなければ「パス」でOK）
```

ユーザーの説明を受けたら Step 4 へ（パスでも可）。

#### Step 4: 3軸ルーブリック採点

`references/rubric.md` に従い accuracy / reasoning / completeness を 0.0-1.0 で付ける。問題タイプの重み付けで最終スコア算出。

#### Step 5: 3層フィードバック + 解説 + 模範回答

`references/explanation-guide.md` に従い、課題ファイルの `## 採点` / `## 解説` / `## 模範回答` セクションを更新する:

- **Feed-up**（目標）: 1行
- **Feed-back**（差分）: ユーザーの回答に固有の指摘
- **Feed-forward**（次の一手）: 具体ヒューリスティック1つ
- **例え話・アナロジー or ステップ展開 or 構造図** を必ず添える
- **模範回答** を `<details>` で展開できる形で
- **複数課題（`### Part X`）のときは `## 解説` を本文と同じ `### Part X` 見出しで区切る**（UI が各課題の解答欄直下に表示するため）。`## 模範回答` は生成時に既に Part ごとに区切られているはずなので、その構造を崩さない。`### Part` に紐付かない全体総評は `## 採点` に書く

ユーザーの自己説明と模範解説の **差分** を必ず明示する（誤概念の固定化を防ぐため）。

#### Step 6: README.md の更新

- `Last updated`: 現在時刻
- `Profile > Strong / Weak`: 新タグを重複なくマージ
- `Recent scores`: 最新スコアを末尾に追加（5件で循環）
- `Stage` / `Current Level` を直近5問平均で必要なら調整（levels.md）

#### Step 7: GLOSSARY.md の更新（理解の証拠があるときのみ）

回答・自己説明の中でユーザーが **概念を正しく使えた証拠** がある用語を `GLOSSARY.md` の `## Terms` に昇格させる。

- 用語集は「圧縮された知識の記録」であって、学習用の辞書ではない。**触れただけの用語は載せない**
- 定義は 1-2 文（「何か」だけ。用途説明は書かない）。同義語が複数あれば最適な1つを選び、他は `_Avoid_` に列挙
- 根拠の lesson 番号を `_Evidence_` に記録
- ユーザーの理解が深まったら定義を改訂し、古い記述を残さない

書式の詳細は `references/knowledge-assets.md`。Spaced Review では「この用語を自分の言葉で定義してください」のような glossary 由来の出題に流用できる。

#### Step 8: INSIGHTS.md への気づき記録（非自明なもののみ）

採点中に以下のいずれかを観察したら、`INSIGHTS.md` に **1-3 文** で追記する:

1. **実証的な理解**: 単なる接触ではなく、概念を正しく活用できた証拠
2. **事前知識の開示**: ユーザーが「それはもう知っている」と述べた領域
3. **誤概念の訂正**: 以前の勘違いが理由ごと正された
4. **Mission の変化**: 学習を通じて関心・目標がずれてきた（README の Mission 更新も提案する）

記録 **しない** もの: 単に扱った内容、glossary に既出の定義、セッションの活動ログ。該当がなければこの Step はスキップ。書式は `references/knowledge-assets.md`。

#### Step 9: curriculum.md の更新

- 該当 lesson のチェックボックスを `[ ]` → `[x]` に
- 必要なら Spaced Review を追加

#### Step 10: FB ルール抽出（`.study/<topic>/FEEDBACK.md`）

ユーザーが提出時に Web UI で残した FB（タグ + 自由記述）は、サーバーが `FEEDBACK.md` のエビデンスログに append 済み。採点フローの最後で **未処理ログをルールに昇格** させる。

1. `.study/<topic>/FEEDBACK.md` を読み込む。`critic_state: pending` のエントリが 1 件でもあれば次へ、無ければスキップ。
2. **FB-Critic サブエージェントを起動**（`references/agent-prompts.md` の「FB ルール抽出」セクションを参照）。pending ログ全部 + 既存ルール一覧 + Profile を渡す。
3. 戻ってきた `rule_proposals` を処理:
   - `action: new` → `FEEDBACK.md` の YAML `rules` 配列に追加（id は `rule-NNN` 連番、`created`, `evidence_refs` も埋める）。**承認不要、自動**。
   - `action: update` / `delete` → **必ず chat でユーザーに承認を取る**。承認されたら反映、却下なら無視、修正案が来たらそれを採用。
4. 処理済みログの `critic_state: pending` を `processed: <rule_id>` に書き換える。
5. 採点メッセージの末尾に簡潔に報告:
   ```
   📚 FB を反映しました: 新ルール 2件追加（rule-007, rule-008）。
   ```

**Profile (README.md) と FEEDBACK.md は別管理**。Profile は診断時に決定する静的な
Strong/Weak、FEEDBACK.md は学習中に動的に成長するトピック固有ルール。FB-Critic は
両方を読むが、書き込むのは FEEDBACK.md のみ。Profile の更新は Step 6 で別途行う。
**INSIGHTS.md とも別物**: FEEDBACK.md は「ユーザーが明示的に残した要望」、INSIGHTS.md は
「採点者が観察した学習上の気づき」を貯める（Step 8）。

#### Step 11: 次 lesson 生成

`curriculum.md` の次未完了項目に基づき、Phase 3 の冒頭に戻る。

**重要**: Generator/Critic は `FEEDBACK.md` の YAML `rules` と `INSIGHTS.md` を必読する
（`references/agent-prompts.md` のプロンプト雛形参照）。
Step 8-10 で記録されたルール・気づきは次の課題生成から有効になる。

### 適応制御

直近 5問の正答率移動平均で Stage / Level を調整。詳細は `references/levels.md`:

| 直近5問平均 | 動作 |
|---|---|
| 0.85+ | 難度上げ、Stage 進行を加速 |
| 0.70-0.85 | 維持（学習効率の窓） |
| 0.50-0.70 | 維持＋ヒント強化 |
| <0.50 | Stage 戻し or 基礎強化セクション挿入 |

## Phase 4: 終了

終了要求を受けたら:

1. `README.md` の `Ended` に日時セット
2. ファイル全体を読み込んで集計:
   - 総 lesson 数、平均スコア
   - Stage 別進捗、Level 推移
   - 最終 Strong / Weak タグ
   - Spaced Reviews の達成状況
3. `README.md` 末尾に `## Summary` セクションを追記
4. ユーザーに **次回の推奨スタート** を提示:
   - 次に取り組むべき lesson 番号
   - 目標保持期間に基づく次回ログイン推奨日

## Web UI（ローカル localhost）

md ファイルが読みづらい・回答記入しにくいので、ブラウザで lesson を見て回答できる **Flask 製ローカル UI** を同梱している（`scripts/server.py`）。起動・停止は実行環境の UI 起動アダプターを通じて行う。

### UI 起動アダプター

ユーザーが「UI で見たい」「ブラウザで」と発話したら、利用可能な UI 起動アダプターを使う。コマンドアダプターでは `/study-ui` が以下を自動で行う:

1. venv が無ければ `scripts/bootstrap.sh` を呼んで作成 + 依存（flask / markdown / pymdown-extensions）インストール
2. 既起動チェック（PID ファイル）— 起動済みなら既存 URL を案内
3. 8765 から空きポートを探して bind
4. nohup でバックグラウンド起動、PID とログを `scripts/` 配下に保存
5. `http://127.0.0.1:<port>` をユーザーに案内

ユーザーが `--port 9000` のような引数を付けて呼んだ場合はその固定ポートを使う。

### UI 停止アダプター

ユーザーが「UI 止めて」「終わり」と発話したら、利用可能な UI 停止アダプターを使う。コマンドアダプターでは `/study-ui-stop` が `scripts/stop.sh` を通じて PID ファイルを読み、`kill -TERM`、3秒待っても止まらなければ `kill -KILL` を実行する。

### スキルから直接 server を起動しない

ユーザーが UI を希望した場合、SKILL 側から直接 `python3 server.py` をシェルで起動しないこと。理由:

- プロセス管理（PID / ポート衝突 / 多重起動）の責務はシェルスクリプトに集約してある
- UI 起動アダプターを使えば idempotent に処理される（ユーザーが何度叩いても安全）
- 直接起動するとゾンビ化や PID ファイル不整合の原因になる

代わりに利用可能な UI 起動アダプターを案内する。

### 機能

| ビュー | URL | 内容 |
|---|---|---|
| セッション一覧 | `/` | `.study/` 配下の全トピック |
| ダッシュボード | `/<topic>/` | README + 進捗バー + Profile + ファイル一覧 |
| カリキュラム | `/<topic>/curriculum` | curriculum.md レンダリング |
| 用語集 | `/<topic>/glossary` | GLOSSARY.md レンダリング（存在する場合のみ） |
| リソース | `/<topic>/resources` | RESOURCES.md レンダリング（存在する場合のみ） |
| 診断問題 | `/<topic>/diagnostic/<file>` | 問題本文 + 回答記入フォーム + ヒント + 採点結果 |
| Lesson | `/<topic>/lessons/<file>` | 同上 |

ユーザーが回答を提出すると、`## 回答欄` セクション直下が **書き戻される**。回答保存後は確認画面で自己説明を任意で追加し、Codex に採点を依頼するか、手動採点アダプターへ採点を依頼するかを選べる。Mermaid / コードハイライト / ダーク・ライトテーマ対応。

### Codex App Server との連携（localhost のみ）

UI は `codex app-server --stdio` を標準ライブラリの JSONL クライアントから必要時だけ起動できる。既定の backend は `auto` であり、ページ表示・ステータス表示・回答保存だけでは Codex を起動しない。ユーザーが「Codex で診断を始める」「Codex で採点する」などの明示ボタンを選んだ時だけ、次の固定操作を FIFO の単一 worker で実行する。

Codex App Server では外部ツール、MCP、サブエージェント、ネストした Codex を呼び出さない。Generator、Critic、FB-Critic は、同じ turn 内で順番に検討する論理的な役割として実行する。Claude Code の手動採点アダプターだけは Agent tool による分離実行を使える。

| 操作 | 成果 |
|---|---|
| `session_start` | セッション資産と最初の診断問題を作成 |
| `diagnostic_grade` / `diagnostic_accept` | 診断を採点し、合意後にカリキュラムを作成 |
| `curriculum_revise` / `curriculum_accept` | カリキュラムの修正または最初の lesson 作成 |
| `lesson_grade` / `spaced_review` | 採点・適応更新または別バリエーションの復習問題作成 |
| `session_end` | README の終了情報と最終サマリを更新 |

- 各 job は新しい thread を使い、プロジェクト root を cwd、`workspace-write` を書込み範囲とする。プロンプト・cwd・パスはサーバーが固定操作から組み立て、ブラウザは任意値を渡せない
- Codex の追加質問は UI の質問カードで回答する。承認は allow / deny / cancel の一回限りで、`.study/` 外へのファイル操作要求は自動拒否する
- job のキュー・進捗・SSE イベントはメモリだけに置く。学習の永続データは引き続き Markdown ファイルであり、server 再起動後は Markdown を見て再開する
- final response は `status`、`summary`、`resultPath`、`nextAction` だけを持つ JSON 形式に限定し、UI には短い commentary だけを表示する。思考過程、コマンド、ログは表示・保存しない
- Codex が未導入、未認証、または Study Loop スキルを検出できない場合は回復案を表示し、手動保存を止めない

コマンドアダプターでは `/study-ui --backend auto|codex|manual` で backend を選べる。`manual` は Codex を起動せず、Markdown を唯一の正とする手動採点フローを使う。UI は `127.0.0.1` / `localhost` / `::1` にしか bind しない。すべての変更リクエストは CSRF と同一 origin を検証する。

### 手動採点アダプター（Claude Code の例）

- **Web UI は md の表示・編集 UI**。学習の永続状態は md 側だけが持つ
- ユーザーが Web で回答を提出 → md が更新される → **手動採点アダプターに「採点して」と依頼** → アダプターが md を読み込み、採点・解説を更新 → ユーザーが Web をリロードで採点表示
- Codex 連携を使わない場合、回答確認画面の手動採点を選ぶか、`--backend manual` を選ぶ

### Anti-Patterns（Web UI 周り）

- **ブラウザから任意の Codex 指示を渡す** — UI は固定の学習操作だけを選べる。任意 prompt / cwd / path は App Server に渡さない
- **サーバーに学習状態を持たせる** — md ファイルがシングルソース。Codex job 状態は再起動で失われる一時状態であり、学習記録の代わりにしてはならない
- **回答欄以外を UI で編集可能にする** — 採点・解説・模範回答は採点アダプターが更新する部分なので UI からは表示のみ
- **常駐サーバーにする** — ユーザーが必要な時に手で起動・停止。複雑な常駐管理は避ける

## References

| File | 内容 |
|---|---|
| `references/learning-science.md` | エビデンスベース基盤（7原則 + URL ソース） |
| `references/curriculum-design.md` | カリキュラム生成アルゴリズム（Stage 配分、Spacing 計算、Interleaving 切替） |
| `references/explanation-guide.md` | 解説の書き方（例え話、Self-Explanation、Dual Coding、わからない対応） |
| `references/levels.md` | 5段階レベル + Bloom 副軸、診断アルゴリズム、適応制御（70-85% 窓） |
| `references/rubric.md` | 3軸ルーブリック、3層フィードバック、わからない時のスコアリング |
| `references/question-types.md` | 出題タイプカタログ、Stage 別配分、worked example の3段階、Faded 設計指針 |
| `references/knowledge-assets.md` | Mission / RESOURCES.md / GLOSSARY.md / INSIGHTS.md の書式と運用ルール（teach スキル由来） |
| `references/agent-prompts.md` | Generator-Critic ループ + FB-Critic（FB ルール抽出）のプロンプト雛形・合格基準・リトライ制御 |
| `scripts/server.py` | Flask 製の Web UI 本体 |
| `scripts/codex_app_server.py` | 標準ライブラリだけで実装したローカル Codex App Server JSONL クライアント |
| `scripts/jobs.py` | 固定操作のみを FIFO 実行するメモリ内 job manager |
| `scripts/templates/`, `scripts/static/` | UI テンプレートとアセット |
| `scripts/requirements.txt` | UI の依存（flask, markdown, pymdown-extensions） |
| `scripts/bootstrap.sh` | venv + 依存インストール（idempotent） |
| `scripts/start.sh` | UI 起動（ポート選定、PID 管理） |
| `scripts/stop.sh` | UI 停止（PID ファイル経由でグレースフル） |
| `commands/study-ui.md` | UI 起動コマンドアダプター定義 |
| `commands/study-ui-stop.md` | UI 停止コマンドアダプター定義 |

## Anti-Patterns

学習効率を破壊するので絶対に避ける:

- **「わからない」回答に解説なしで次に進む** — ユーザーのフィードバックで明示された禁忌。模範回答 + 解説を **必ず** 提示する
- **解説に例え話・アナロジーを入れない** — 抽象だけの解説は記憶に残らない（dual coding 効果が消える）
- **「すばらしい！」「がんばりました！」だけ** — 中身ない praise は *d* < 0.20、効果ほぼゼロ
- **MCQ ばかり出す** — recognition は recall より効果が薄い、ショートカットされる
- **課題のコメントに答えを書く** — 「`const` で宣言する」「`string` を受け取って `string` を返す」のような解答指示型コメントは、空欄が写経に堕ちる。コメントには **状況・要件** のみを書き、「何を判断させるか」は補足コメントで示唆する。詳細は `references/question-types.md` の「Faded Worked Example の設計指針」
- **Generator-Critic ループをスキップして 1パスで作問する** — 規範違反（コメントに答え混入、写経テスト等）が頻出する。診断問題でも通常 lesson でも必ずループを通す。詳細は `references/agent-prompts.md`
- **Stage を飛ばす** — Foundation 不十分で Practical に進むと self-explanation も elaborative interrogation も効かない
- **Spacing を考慮せずカリキュラムを詰込む** — 短期成果は出るが長期保持が壊滅
- **学習者の主観だけで難度調整** — fluency 錯覚に汚染されている。スコア推移を主軸に
- **同じ問題で復習する** — recognition のショートカットが起きる。同概念の別バリエーション
- **診断と通常学習を同じフローで処理** — 役割が違うので分離する（ユーザーのフィードバック反映）
- **解説モードに陥る** — ユーザーが回答する前に答えを延々と説明しない。**まず課題ファイルを出す**
- **Highlighting / 再読み / Summarization を能動推奨する** — Dunlosky 2013 で低効用に分類されている
- **事実系トピックをモデルの記憶だけで出題する** — 歴史・資格試験・最新仕様などは誤った事実が混入する。RESOURCES.md を先に作り、出題・解説の事実はソースに依拠する（"Never trust parametric knowledge"）
- **理解の証拠なしに glossary へ用語を追加する** — 用語集が「読んで学ぶ辞書」に堕ちる。回答内で正しく使えた用語だけを昇格させる

## ユーザーへの配慮

- 集中切れの兆候（連続スキップ、雑な回答）が見えたら一度休憩を提案する
- セッションが長引いてきたら自発的に「ここまでで一区切り？」と確認
- 連続失敗時は **責めない**。Stage 戻しを「合うレベルに調整します」と前向きに伝える
- 連続成功時は **具体的に** 褒める（「○○の判定が正確でした」のような中身ある praise のみ）
- 学習科学のエビデンスを楯にして無理を通さない（疲労時は休む方が長期的に効率が良い）
