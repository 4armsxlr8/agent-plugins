# Learning Science: Study Loop のエビデンスベース基盤

このスキルの設計判断はすべて、教育心理学のメタ分析・システマティックレビューに基づく。憶測や経験則ではなく、効果サイズ（Cohen's *d* / Hedges' *g*）が検証された原則のみを採用する。

## 採用する 7原則（効果サイズ順）

### 1. Feedback の質 — *d* ≈ 0.70–1.00（強）

**研究**: Hattie & Timperley (2007) "The Power of Feedback"; Wisniewski, Zierer & Hattie (2020) "The Power of Feedback Revisited".
**主要発見**: 高情報フィードバックは *d* ≈ 0.99、単なる praise / punish は *d* < 0.20。フィードバックは「Feed-up（目標）」「Feed-back（現状との差）」「Feed-forward（次の一手）」の3層を満たすと最大効果。
**Study Loop への適用**:
- 採点後フィードバックは必ず **3層構造** で書く（`references/rubric.md`）
- 「すばらしい！」「がんばりました！」のような中身ない賞賛は出さない
- 即時 vs 遅延フィードバックは内容ほど重要でない（最新メタは「内容差が支配的」）

**ソース**:
- https://journals.sagepub.com/doi/abs/10.3102/003465430298487
- https://pmc.ncbi.nlm.nih.gov/articles/PMC6987456/

---

### 2. Retrieval Practice / Testing Effect — *d* ≈ 0.50–0.80

**研究**: Roediger & Karpicke (2006) "The Power of Testing Memory"; Karpicke (2006) "Test-Enhanced Learning".
**主要発見**: 遅延テストにおいて「テスト > 再読」が一貫して観測される。recall（自由想起）は recognition（多肢選択）より効果が大きい。フィードバックがあると効果がさらに増幅。
**Study Loop への適用**:
- 出題は **cued recall / free recall を優先**、多肢選択は補助のみ
- 同概念を時間を空けて 2-3回テストする（spacing と組合せ）
- 誤答時には必ず正解＋簡潔な解説をフィードバック

**ソース**:
- http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Karpicke-2006_PPS.pdf
- https://pubmed.ncbi.nlm.nih.gov/16507066/

---

### 3. Self-Explanation Effect — *g* ≈ 0.55

**研究**: Bisra et al. (2018) "Inducing Self-Explanation: A Meta-Analysis" (69 効果量 / 64 研究).
**主要発見**: 「自分の言葉でなぜそうなるかを説明させる」プロンプトは、用意された解説を読ませるより効果が高い。worked example の途中ステップで挿入すると特に有効。
**Study Loop への適用**:
- 模範解説を提示する **前** に「なぜこの答えになると思いますか？」を必ず挟む
- ユーザの自己説明と模範解説の **差分** を提示する（誤概念の固定化を防ぐため、放置しない）

**ソース**:
- https://link.springer.com/article/10.1007/s10648-018-9434-x

---

### 4. Worked Examples + Faded（初学者で *d* ≈ 0.5–1.0）

**研究**: Sweller, van Merriënboer, Paas 系の Cognitive Load Theory; Kalyuga et al. (2003) "The Expertise Reversal Effect".
**主要発見**: 初学者には完全な解答付き例題（worked example）→ 部分穴埋め（faded）→ 自力問題、と段階的に手放す方が効果的。**ただし習熟後はむしろ問題演習の方が効く（Expertise Reversal Effect）**。
**Study Loop への適用**:
- Stage 1（Foundation）では worked example を必ず提示してから類題出題
- Stage 2（Practical）では faded example（途中まで解いて穴埋め）
- Stage 3（Design）以降は自力問題のみ（過剰なガイダンスは負荷増になる）

**ソース**:
- https://www.uky.edu/~gmswan3/EDC608/Kalyuga2007_Article_ExpertiseReversalEffectAndItsI.pdf
- https://en.wikipedia.org/wiki/Expertise_reversal_effect

---

### 5. Distributed Practice / Spacing — *d* ≈ 0.4–0.9

**研究**: Cepeda et al. (2006) "Distributed practice in verbal recall tasks: A review and quantitative synthesis" (839 比較); Cepeda et al. (2008) *Psychological Science*.
**主要発見**: 最適な ISI（学習間隔）は **目標保持期間（Retention Interval）の 5–20%**。例えば 1ヶ月後のテストなら ISI は 1-6日、1年後なら数週間〜1ヶ月。massed（一気に詰込み）より一貫して優位。
**Study Loop への適用**:
- セッション開始時に「いつまでにこの状態でいたいか」をユーザーに確認
- カリキュラムの復習問題タイミングを目標保持期間の 10-15% で配置
- SM-2 系の固定間隔よりも、**目標保持期間ベースのスケジューラ** を採用

**ソース**:
- https://pubmed.ncbi.nlm.nih.gov/16719566/
- https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf

---

### 6. Interleaved Practice — *g* ≈ 0.42

**研究**: Brunmair & Richter (2019) "Similarity matters: A meta-analysis of interleaved learning"; Rohrer et al. (2020) RCT in mathematics.
**主要発見**: 類似カテゴリの **弁別** が必要な領域（数学の問題タイプ識別、文法の類義語等）で特に有効。一方、解説文の単純学習や、未習得スキルの磨き込みでは blocked（同種反復）の方が良い。
**Study Loop への適用**:
- 新単元導入直後は **blocked（同種を連続）** で習得促進
- 単元理解後は **interleaved（複数単元混在）** に切替えて定着促進
- Stage 1: blocked / Stage 2 以降: interleaved 中心
- ⚠️ 学習者は interleaving を「効いている感じがしない」と訴えやすい（メタ認知の錯覚）が、エビデンスを優先する

**ソース**:
- https://pubmed.ncbi.nlm.nih.gov/31556629/
- https://gwern.net/doc/psychology/spaced-repetition/2019-rohrer.pdf

---

### 7. Elaborative Interrogation — *d* ≈ 0.42

**研究**: Dunlosky et al. (2013) 内レビュー; Visible Learning Metax 集計（24 研究 / 15,450 名）.
**主要発見**: 「なぜこの事実は真か」を学習者に問わせると、事実知識の保持が向上。**ただし prior knowledge が必要** — 完全な未経験ドメインでは自己生成説明がデタラメになり効果が薄い。
**Study Loop への適用**:
- Stage 1（完全初学者）では worked example 中心、"Why?" プロンプトはオフ
- Stage 2 以降で "Why?" プロンプトを混ぜる（「なぜこの実装が動くか説明してみてください」など）

**ソース**:
- https://www.visiblelearningmetax.com/influences/view/elaborative_interrogation

---

## Desirable Difficulties (Bjork) — メタ原則

**研究**: Bjork & Bjork (2011, 2020) "Making things hard on yourself, but in a good way".
**主要発見**: 学習中の **Performance（その場のできばえ）** と **Learning（長期保持）** は乖離する。困難は短期パフォーマンスを下げるが長期保持を上げる。spacing / retrieval / interleaving / generation はすべてこの原理の現れ。
**Study Loop への適用**:
- 難度は **「直近正答率 70-85%」の窓** を狙う（成功すぎず失敗すぎず）
- ユーザーが「簡単すぎる」「効いてる感じがしない」と訴えても、エビデンスベースのループを維持する設計に
- 完璧な fluency は学習が止まっているサイン

**ソース**:
- https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf

---

## 採用しない手法（低効用）

Dunlosky et al. (2013) のレビューで **低効用** に分類された手法は Study Loop では能動推奨しない。

| 手法 | 効用 | 理由 |
|---|---|---|
| Highlighting / Underlining | 低 | 受動的な処理。記憶への変換にならない |
| Rereading | 低 | fluency の錯覚を生むだけで保持に寄与少 |
| Summarization | 低 | 適切な訓練なしでは保持促進が薄い（要約スキル自体が要訓練） |
| Imagery for Text | 低 | 抽象テキストには適用困難 |
| Keyword Mnemonic | 低 | 限定領域でしか効果がない（外国語語彙等） |

## Bloom's Taxonomy の位置付け

Bloom 階層（Remember / Understand / Apply / Analyze / Evaluate / Create）は **学習効果のメタ分析対象ではない**（フレームワーク論）。階層性の経験的根拠は弱い（Stanger-Hall 2012 等）。

**Study Loop での扱い**:
- 出題の認知レベル分布を **モニタする道具** として使用（特定階層に偏らないようバランサ）
- カリキュラムの「ロック構造」（下位階層がクリアされないと上位に進めない）には使わない
- 効果サイズベースの 7原則を駆動軸とし、Bloom はその出題タイプを多様化させるための副次指標

詳細: `references/levels.md`

---

## 設計の優先順位

カリキュラム生成・出題・採点で迷ったら、上記原則の **効果サイズ順** で判断する:

1. **Feedback の質** — すべての採点で必ず守る
2. **Retrieval の頻度** — recall を出題の中心に
3. **Self-Explanation** — 解説提示前に「なぜそう思った？」を挟む
4. **Worked Examples の段階手放し** — 習熟度に合わせ fade
5. **Spacing** — 目標保持期間ベースで復習タイミング決定
6. **Interleaving** — 単元理解後に混在出題に切替
7. **Elaborative Interrogation** — Stage 2 以降で "Why?" を混ぜる

7 原則すべてを **同時に最大化しようとしない**（リソースとユーザの集中の限界がある）。Stage と習熟度に応じて **重み付けして** 適用する。詳細は `references/curriculum-design.md`。
