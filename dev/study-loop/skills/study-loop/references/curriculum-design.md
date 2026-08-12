# Curriculum Design: 生成アルゴリズム

`references/learning-science.md` の 7原則を **どう実装するか** をまとめる。カリキュラム生成・課題配置・復習タイミング決定の具体ルール集。

## 生成プロセス

### Step 1: 必要情報の収集

カリキュラム生成前にユーザーから以下を引き出す（簡潔に、選択肢を提示して）:

1. **トピック粒度**: 「TypeScript全般」か「TypeScriptの型推論」か。広すぎても狭すぎても学習設計が困難
2. **目標保持期間 (Retention Interval)**: 「いつまでにこの状態でいたいか」
   - 短期（1-2週間）: 試験直前型 / プロトタイプ実装
   - 中期（1-3ヶ月）: プロジェクト導入 / 業務適用
   - 長期（半年以上）: キャリアスキル化 / 試験合格
3. **目標レベル**: Level 3（実務で書ける）/ Level 4（設計判断ができる）/ Level 5（教えられる・最適化できる）。LLM が「このトピックなら Level 4 まで提案します」と推奨しユーザーの同意を取る
4. **時間予算**: 「1日 30分 × 2週間」など。これでカリキュラムの密度を決める

これらを `README.md` のヘッダーに記録する。

### Step 2: 診断実施 → 現在地の確定

`references/levels.md` の診断アルゴリズムで現在の Level と Strong / Weak タグを推定する。診断は **必ず通常学習と分ける**（後述）。

### Step 2.5: リソース選定（RESOURCES.md の作成）

Stage 配分を考える前に、WebSearch / WebFetch で **信頼できる情報源を 5本前後に厳選** して `RESOURCES.md` を Write する（"Never trust parametric knowledge"）。一次資料・公式ドキュメント・査読済み資料を優先し、各リソースに1行注釈を付ける。書式・選定基準は `references/knowledge-assets.md` 参照。

以降の lesson 生成では、出題・解説の事実をこのソースに依拠させる（Generator / Critic のプロンプトに展開する。`references/agent-prompts.md`）。

### Step 3: Stage 配分の決定

現在 Level → 目標 Level の差から Stage 配分を決める。**3段階構成** が基本:

| Stage | ねらい | 主に使う原則 |
|---|---|---|
| **Foundation** | Level 1-2 の習得 | Worked Examples（完全） / Cued Recall / Blocked Practice |
| **Practical** | Level 3 の習得 | Faded Examples / Free Recall / Self-Explanation / Interleaving 開始 |
| **Design** | Level 4-5 の習得 | 自力課題 / フル Interleaving / Elaborative Interrogation / 評価・設計課題 |

例:
- 現在 Level 1 → 目標 Level 4: Foundation 4本 / Practical 5本 / Design 3本
- 現在 Level 3 → 目標 Level 5: Foundation スキップ or 復習1本 / Practical 3本 / Design 4本

### Step 4: lesson ファイルの粒度

1 lesson = **30-60分で取り組める粒度** が目安。これより大きいと完了感が薄れ、小さいと文脈が断片化する。

各 lesson は単一の **学習目標（learning objective）** を持つ。例:
- ❌ 「TypeScript の型を学ぶ」（広すぎる）
- ✅ 「Generic 関数を type parameter constraints 付きで書ける」（具体的）

### Step 5: curriculum.md 生成

次のテンプレートで `.study/<topic-slug>/curriculum.md` を Write する:

```markdown
# Curriculum: <topic>

## Goal
- **目標保持期間**: <短期/中期/長期、具体期日>
- **目標 Level**: <1-5>
- **時間予算**: <1日 X 分 × Y 日>

## Roadmap

### Stage 1: Foundation (Level 1-2)
- [ ] [001 - <slug>](lessons/001-<slug>.md) <!-- worked example: full -->
- [ ] [002 - <slug>](lessons/002-<slug>.md)
- ...

### Stage 2: Practical (Level 3)
- [ ] [00N - <slug>](lessons/00N-<slug>.md) <!-- faded example -->
- [ ] [00N - <slug>](lessons/00N-<slug>.md) <!-- self-explanation -->
- ...

### Stage 3: Design (Level 4-5)
- [ ] [00N - <slug>](lessons/00N-<slug>.md) <!-- open problem -->
- [ ] [00N - <slug>](lessons/00N-<slug>.md) <!-- design task -->
- ...

## Spaced Reviews
復習タイミング（目標保持期間の 10-15% を初回 ISI とする）:
- [ ] After lesson 003: revisit 001, 002 — at <date>
- [ ] After lesson 006: revisit 004, 005 — at <date>
- ...

## 注意（learning-science 由来）
- 「効いてる感じがしない」と感じても interleaving と spacing は効く（Bjork desirable difficulties）
- 同じ問題を時間を空けて再出題するのは仕様（retrieval practice）
- 「わからない」を許容する。次に進まず必ず解説と模範回答を提示する
```

ユーザーにレビューしてもらい、合意を得てから lesson 生成に進む。

## 課題タイプの Stage 配分

`references/question-types.md` の各タイプを Stage に応じて配分する:

| Type | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| Worked Example (full) | ◎ 主軸 | △ 復習用 | × 不要 |
| Worked Example (faded) | △ 終盤 | ◎ 主軸 | △ 困難領域 |
| Cued Recall | ◎ | ○ | △ |
| Free Recall | △ | ◎ | ◎ |
| Hands-on Code | △ 写経 | ◎ 標準 | ◎ 拡張 |
| Refactor | × | ○ | ◎ |
| Debug | × | ◎ | ◎ |
| Design Mini | × | △ | ◎ |
| Read-and-Explain | △ | ○ | ◎ |
| Compare-by-Example | × | ○ | ◎ |
| Self-Explanation prompt | × prior知識不足 | ◎ | ◎ |
| Elaborative "Why?" | × | ○ | ◎ |

`◎` = 主軸 / `○` = 推奨 / `△` = 補助 / `×` = 推奨しない

## Spacing スケジューラ

Cepeda et al. (2008) の **目標保持期間の 5–20%** を ISI とする原則を実装。

| 目標保持期間 | 推奨初回 ISI | 例 |
|---|---|---|
| 1週間 | 1-2日 | 月曜学習 → 木曜復習 |
| 1ヶ月 | 3-6日 | 1日学習 → 5日後復習 |
| 3ヶ月 | 1-2週間 | 1日学習 → 10日後復習 |
| 1年 | 1-2ヶ月 | 1日学習 → 5週間後復習 |

復習問題は **同じ問題ではなく、同じ概念の別バリエーション** を出す（recognition によるショートカット防止）。

復習で正答率 0.8+ なら次の ISI を 2倍に（成功した spacing は伸ばす）。0.4 以下なら ISI を半分に（再習得が必要）。

## Interleaving の切替

- **新単元導入直後** → blocked（同種反復で習得促進）
- 単元の正答率が安定して 0.8+ になったら → interleaved に切替
- Stage 2 後半以降は基本 interleaved
- ⚠️ 学習者は interleaving を「混乱する / 効いていない」と感じる傾向（Bjork desirable difficulties）。**主観的フィードバックでなくスコア推移** を判断材料にする

## Worked Example の Fading

Stage 1 → Stage 3 で段階的に手放す:

```
Stage 1 (full):     問題 + 完全な解答ステップ + 解説 → 「次はこれを真似て解いて」
                    ↓
Stage 2 (faded):    問題 + 解答ステップの最初2/3 → 「最後の1/3を埋めて」
                    ↓
Stage 2-3 (open):   問題のみ → 自力で全解答
```

**Expertise Reversal Effect** 注意: 中級以上の学習者には worked example は冗長で逆効果。Stage 3 では使わない。

## カリキュラム再生成のトリガー

以下の場合はカリキュラムを **再生成 / 修正** する:

1. 5 lesson 連続で正答率が 0.5 以下 → Stage を1段下げて基礎強化に再配分
2. 5 lesson 連続で正答率が 0.9+ → 難度を上げる、または現 Stage を圧縮
3. ユーザーが「目標を変更したい」と申し出た場合
4. 新しい弱点タグが 3つ以上溜まった場合 → 集中強化セクションを挟む

再生成時は `curriculum.md` を Edit で更新し、変更点をユーザーに説明する（突然変わると混乱するため）。

## アンチパターン

- **3原則以上を同時に最大化しようとする** — 認知負荷オーバー。Stage に応じて 2-3 原則に絞る
- **Stage を飛ばす** — Foundation 不十分で Practical に進むと、Self-Explanation も Elaborative Interrogation も効かない
- **Spacing を考慮せず詰込みカリキュラムを作る** — 短期成果は出るが長期保持が壊滅
- **学習者の主観だけで難度調整する** — 「簡単」「難しい」感覚は fluency 錯覚に汚染されている。スコア推移を主軸に
- **同じ問題で復習する** — recognition のショートカットが起きる。同概念の別バリエーションを作る
