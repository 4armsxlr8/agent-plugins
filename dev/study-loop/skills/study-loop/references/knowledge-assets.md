# Knowledge Assets: Mission / Resources / Glossary / Insights

Matt Pocock 氏の [teach スキル](https://github.com/mattpocock/skills/tree/main/skills/productivity/teach) から取り込んだ「学習を支える土台ファイル」の書式と運用ルール。出題・採点ループ（SKILL.md）を裏から支える 4 つの資産を定義する。

| 資産 | 置き場所 | 役割 | 更新タイミング |
|---|---|---|---|
| Mission | `README.md` の `## Mission` | なぜ学ぶかの羅針盤 | Phase 0 で作成、目標が変わったら改訂 |
| Resources | `RESOURCES.md` | 厳選した信頼できる情報源 | Phase 2 冒頭で作成、随時剪定 |
| Glossary | `GLOSSARY.md` | 理解済み用語の圧縮記録 | 採点 Step 7 で昇格 |
| Insights | `INSIGHTS.md` | 非自明な気づきのログ | 採点 Step 8 で追記 |

## Mission（README.md 内）

学習の「なぜ」を文書化し、すべての出題の題材選びの羅針盤にする。

### 原則

1. **One mission per topic** — 関連のない学習目標は別トピック（別セッション）に分ける
2. **Concrete over abstract** — 「TypeScript がうまくなりたい」ではなく「6月までに社内ライブラリの型定義を自力で書けるようになる」
3. **Push back on vagueness** — ユーザーが Why を説明できなければ、作問に入る前に質問で掘り下げる
4. **Revise when reality shifts** — 目標が変わったら Mission を更新し、古い記述を残さない
5. **Keep it short** — 1画面以内。超えたらそれは Mission ではなく計画

### 出題への反映

- Generator は課題の **題材・シナリオ** を Why / Success looks like に寄せる（抽象的な例題より、ユーザーの現実の文脈）
- **Out of scope** に挙がった領域はカリキュラムにも課題にも入れない（膨張防止）
- Critic は `mission_alignment` で題材のズレを採点する

## RESOURCES.md

> "Never trust parametric knowledge." — 事実はモデルの記憶（パラメトリック知識）ではなく、検証可能なソースから引く。

### 作成タイミングと手順

Phase 2（カリキュラム生成）の **冒頭**、Stage 配分を考える前に作る:

1. WebSearch / WebFetch でトピックの一次資料・公式ドキュメント・定番教材を調査
2. **5本前後に厳選**（"five sharp sources than thirty mediocre ones" — 精選された5本 > 平凡な30本）
3. 各リソースに「何に使うか」の **1行注釈** を必ず付ける（リンクだけでは後で役に立たない）
4. ユーザーにカリキュラムと一緒にレビューしてもらう

### 選定基準

- **優先**: 一次資料、公式ドキュメント、認知された専門家、査読済みの研究、モデレーションの強いコミュニティ
- **排除**: マーケティングを装った教育コンテンツ、出所不明のまとめ記事
- **剪定**: 浅い・誤りが見つかったリソースは消す（堆積させない）
- **Gaps 明示**: 良い資料が見つからない領域は正直に書く（次回の探索対象になる）

### テンプレート

```markdown
# Resources: <topic>

精選した信頼できる情報源。課題・解説の事実はここから引く。

## Knowledge（知識源）

- **<リソース名>** — <URL>
  <1行注釈: 何に使うか、なぜ信頼できるか>

## Wisdom（実践コミュニティ）

- **<コミュニティ名>** — <URL>
  <1行注釈。ユーザーが参加を望まない場合はその旨を記録して推さない>

## Gaps（良い資料が未発見の領域）

- <領域>: <どんな資料を探すべきか>
```

### 出題への反映

- Generator は資料に依拠して事実を書く。**ソースで確認できない固有名詞・数値・年号を断定しない**
- Critic は `fact_grounding` で評価し、ソースと矛盾する事実は **重大違反** とする
- 解説で事実を補強するときは「（出典: RESOURCES.md の○○）」と添えてよい
- `RESOURCES.md` が未作成の場合（プログラミング基礎など低リスクなトピック）でも、Generator には「事実の断定を避ける」指示を渡す

## GLOSSARY.md

> "The glossary is a record of compressed knowledge, not a dictionary the user reads to learn." — 学ぶために読む辞書ではなく、理解した証拠の記録。

### 運用ルール

1. **理解後にのみ追加**: ユーザーが回答・自己説明の中で概念を正しく使えてから載せる（採点 Step 7）
2. **定義は 1-2 文**: 「何か」だけを書く。用途説明・背景話は書かない
3. **言い換えの統一**: 同義語が複数あるとき最適な1つを選び、他は `_Avoid_` に列挙。以後の課題・解説はその表記に揃える
4. **相互参照**: 定義文の中では glossary 既出の用語を優先的に使う
5. **自然な分類**: 意味的なまとまりができたら `### サブ見出し` を切る
6. **曖昧さの明示**: 業界で用法が揺れている用語はその旨を書く
7. **継続改訂**: 理解が深まったら定義を上書きし、古い記述を残さない

### テンプレート

```markdown
# Glossary: <topic>

ユーザーが正しく使えた用語だけを載せる圧縮知識の記録（学習用の辞書ではない）。

## Terms

**<用語>**: <定義 1-2 文>
_Avoid_: <避ける言い換え（あれば）>
_Evidence_: <根拠の lesson 番号>
```

### 出題への反映

- Spaced Review の出題ネタに流用できる（「この用語を自分の言葉で定義してください」= retrieval practice）
- Generator / Critic は用語の表記を glossary に揃える

## INSIGHTS.md

ADR（Architecture Decision Record = 設計判断の記録）の学習版。「非自明な教訓・重要な洞察・次の作問を導く事前知識」を 1 エントリ 1-3 文で残す。

### 記録する場面（採点 Step 8）

1. **実証的な理解**: 単なる接触ではなく、概念を正しく活用できた証拠が出た
2. **事前知識の開示**: ユーザーが「それはもう知っている」と述べた
3. **誤概念の訂正**: 以前の勘違いが理由ごと正された
4. **Mission の変化**: 学習を通じて関心・目標がずれてきた（README の Mission 更新も提案）

### 記録しないもの

- 単に「扱った内容」（それは curriculum.md のチェックボックスの仕事）
- glossary に既出の定義
- セッションの活動ログ（「今日は3問解いた」等）

### テンプレート

```markdown
# Insights: <topic>

非自明な気づきの記録（ADR の学習版）。Generator / Critic が必読。

## <YYYY-MM-DD> <短いタイトル>

<1-3文: 観察した事実と、今後の出題に与える影響>
```

例:

```markdown
## 2026-06-10 conditional types は実務経験あり

診断 Q3 で infer を使った型を即答。Foundation での conditional types 出題は
スキップし、Stage 2 から distributive 周りの edge case に絞ってよい。
```

### 出題への反映

- Generator は **既知と記録された内容をゼロから出題しない**（時間の無駄 + 退屈）
- 訂正済みの誤概念は、放置せず **別バリエーションで再確認** する（固定化の防止）
- FEEDBACK.md とは別物: FEEDBACK.md は「ユーザーが明示的に残した要望」、INSIGHTS.md は「採点者が観察した気づき」

## アンチパターン

- **リンクだけの RESOURCES.md** — 注釈がないと次のセッションで使い物にならない
- **30本の平凡なリソース** — 多いことに価値はない。5本に絞る勇気を持つ
- **glossary を先回りで埋める** — 「これから学ぶ用語リスト」になった時点で役割が壊れる
- **insights が活動ログ化する** — 「今日は○○をやった」は気づきではない
- **Mission が計画書化する** — 1画面を超えたら curriculum.md と役割が重複している
