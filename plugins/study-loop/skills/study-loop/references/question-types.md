# Question Types

`references/learning-science.md` の Retrieval Practice / Worked Examples / Interleaving の知見に基づき、効果サイズの大きい出題タイプを優先する。**recognition（多肢選択）より recall（自由想起）を主軸** にする。

## Recall の階層

Retrieval Practice の効果は recall 形式で最大（*d* ≈ 0.5-0.8、Roediger & Karpicke 2006）。Study Loop は基本的に recall を主軸にする。

| 形式 | 例 | 効果 | 使いどころ |
|---|---|---|---|
| **Free Recall** | 「○○について知っていることを書き出してください」 | 最大 | 復習、定着確認、Stage 2-3 |
| **Cued Recall** | 「△△の場面では何を使う？」（ヒント付想起） | 大 | Stage 1-2、初回学習 |
| **Recognition (MCQ)** | 4択で選ぶ | 小 | 試験対策のみ補助、Study Loop では基本不使用 |

⚠️ **MCQ を Study Loop ではほぼ使わない**: recognition は recall より効果が薄く、ショートカット（消去法）で答えが当たってしまう。資格試験対策で本番形式を再現したい場合のみ補助的に使う。

## Worked Example の3段階

`references/curriculum-design.md` に基づき、Stage に応じて段階的に手放す:

| 形式 | 内容 | Stage |
|---|---|---|
| **Full Worked Example** | 完全な解答ステップ + 解説。「次はこれを真似て解いて」 | 1 (Foundation) |
| **Faded Worked Example** | 解答ステップの一部が `___` 空欄。残りを埋めさせる | 2 (Practical) |
| **Open Problem** | 問題のみ。自力で全解答 | 2 後半 - 3 (Design) |

**Expertise Reversal Effect**: Level 4-5 学習者には worked example は逆効果。Stage 3 では使わない。

## タイプ一覧

| Type | Bloom | 目的 | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|---|---|
| `worked-full` | Apply | 完全例題＋類題 | ◎ | △ | × |
| `worked-faded` | Apply | 部分穴埋め例題 | △ 終盤 | ◎ | △ |
| `cued-recall` | Remember/Understand | ヒント付き想起 | ◎ | ○ | △ |
| `free-recall` | Understand/Apply | 自由想起 | △ | ◎ | ◎ |
| `predict-output` | Apply | コード/数式の出力予測 | ○ | ◎ | ◎ |
| `hands-on` | Apply/Create | 実際にコードを書いて動かす | △ 写経 | ◎ | ◎ |
| `find-bug` / `debug` | Analyze | バグ特定・修正 | × | ◎ | ◎ |
| `read-and-explain` | Analyze | 既存コード読解 | × | ○ | ◎ |
| `refactor` | Evaluate/Create | より良い書き方に変える | × | ○ | ◎ |
| `extend` | Apply/Create | 既存コードに機能追加 | × | ○ | ◎ |
| `compare-by-example` | Analyze/Evaluate | 実例で比較 | × | ○ | ◎ |
| `critique` | Evaluate | 批判的評価 | × | △ | ◎ |
| `design-mini` | Create | 制約下のミニ設計 | × | △ | ◎ |
| `reproduce` | Create | 動作の再現コードを書く | × | ○ | ◎ |
| `mcq` | Remember | 多肢選択（資格試験補助のみ） | △ | △ | × |

`◎` = 主軸 / `○` = 推奨 / `△` = 補助 / `×` = 不適合

## 課題ファイルとして書く（座学にしない）

ユーザーのフィードバックに沿い、**チャットで一問一答** ではなく **md ファイル形式の問題用紙** で出題する。

各 lesson は `.study/<topic>/lessons/<NNN>-<slug>.md` に書き出され、ユーザーが **回答欄に記入する** 形式:

```markdown
# Lesson 005: 配列の最初の要素を安全に取り出す
Level 3 / apply / hands-on / Stage 2

## 学習目標
- Generic 関数で型安全に配列処理ができる
- エッジケース（空配列）を最初に書き出す習慣をつける

## 課題
TypeScript で `head<T>(arr: T[]): T | undefined` を実装してください。
- 空配列の場合は `undefined` を返す
- それ以外は最初の要素を返す
- 型パラメータ `T` を使うこと

## 回答欄
<!-- ここに記入してください。書き終わったら「採点して」と伝えてください -->

```typescript

```

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
<details><summary>展開して見る</summary>...</details>
```

ユーザーが回答 → 「採点して」と発話 → LLM が `## 採点` / `## 解説` / `## 模範回答` を `references/rubric.md` と `references/explanation-guide.md` に従い Edit で埋める。

## トピック適合の指針

- **プログラミング**: `hands-on` / `predict-output` / `find-bug` / `refactor` / `extend` を主軸。`design-mini` で設計判断
- **語学**: `cued-recall`（語彙） / `predict-output`（文法構文の出力） / `compare-by-example`（類義語実例） を主軸
- **数学**: `predict-output`（計算） / `worked-full`（解法手順習得） → `worked-faded` → `hands-on`（自力解法）
- **知識・歴史**: `free-recall` / `compare-by-example` / `critique` / `read-and-explain`
- **資格試験**: `mcq` を本番形式再現で補助、ただし学習効果のために `cued-recall` / `free-recall` も混ぜる

## 良い問題のチェックリスト

問題を出す前に自問する:

1. **学習目標が明確か?** lesson ヘッダーに 1-2 行で書けるか
2. **答えが一意に定まるか?** または複数正解を許容するか明示しているか
3. **直近正答率 70-85% の窓に合う難度か?** （desirable difficulties）
4. **採点しやすいか?** 自由記述すぎると客観評価が困難
5. **過去問と被っていないか?** `lessons/` 内の既存ファイルを Glob して確認
6. **トピックの偏りはないか?** 同じサブトピックばかり出していないか
7. **Stage に合った課題タイプか?** `Stage 1 で hands-on` `Stage 3 で worked-full` などズレていないか
8. **問題文は 1スクリーンに収まるか?** 前提と問いを明確に分割

## 悪い問題（避ける）

- **二重否定や曖昧な指示語**: 「どれがふさわしくないとは言えないか?」のような構文
- **意地悪なトリック**: 学習を阻害する。**学びになる** 問題を選ぶ
- **作為的すぎる例**: 現実にはまず出会わないコーナーケース連発
- **採点が水掛け論になる主観問題**: 「○○の良さを語れ」など。比較の軸を明示すれば可
- **複合問題の詰め込み**: 1問で5つのことを問わない。分割して連続出題する
- **MCQ への過度な依存**: recall を奪うので Study Loop では原則使わない
- **答えをコメントに書く**: 「`const` で宣言する」「`string` を受け取って `string` を返す」のような **解答指示型** コメントは、空欄が **写経** に堕ちる。後述「Faded の設計指針」を厳守
- **タイピング演習化**: 思考要素ゼロで、見たまま書き写すだけの空欄。空欄ごとに「ここで何を判断させたいか」を必ず持たせる

## Faded Worked Example の設計指針

faded は最も失敗しやすい形式である。空欄の作り方を誤ると、学習効果ゼロの **写経テスト** に堕ちる。以下の規範を守る。

### 設計の4ステップ

1. **学習目標を1つに絞る**: その問題で何を判断させたいかを1つに決める。「変数宣言の使い分け」を問う問題で、同時に「型注釈」「初期値」も問わない
2. **判断ポイントだけを空欄にする**: 学習目標に対応する箇所のみ `___` にする。それ以外は埋めて出す
3. **コメントには「状況・要件」のみ書く**: 「再代入の予定はない」「実行コストを最小化したい」のような **状況** を書く。「`const` で宣言する」「`number[]` と書く」のような **答えそのもの** は禁止
4. **空欄の意味を明示する**: 何を判断するかを補足コメントで添える。「← const か let か？」「← 引数の型」のように

### 良い例 / 悪い例の対比

**学習目標: `const` と `let` の使い分け**

❌ 悪い faded（解答指示型コメント）:
```typescript
// city という変数を宣言し、文字列 "Osaka" を入れる。再代入したくないので const で。
______ city ______ = "Osaka";
```
- コメントに「const で」と答えが書かれている
- ユーザーは判断していない、ただ書き写している

✅ 良い faded（状況のみ）:
```typescript
// city は "Osaka" を保持する。この後 city が指す都市は変更しない。
______ city = "Osaka";
//  ↑ const か let か？再代入の有無から判断
```
- コメントは **状況** のみ
- 補足コメントで判断ポイントを示唆（答えは出さない）

---

**学習目標: 関数の型注釈**

❌ 悪い faded:
```typescript
// greet という関数。string を受け取って string を返す。中身は `Hello, ${name}!`。
function greet(______): ______ {
  return ______ ;
}
```
- 引数の型・戻り値の型・関数の中身、すべてコメントで言ってしまっている
- 写経でしかない

✅ 良い faded:
```typescript
// 名前を受け取って "Hello, Honoka!" のような挨拶文を生成する関数 greet。
// 関数シグネチャに型注釈を明示すること（推論に任せない）。
// 使用例: greet("Honoka") → "Hello, Honoka!"
function greet(______): ______ {
  return ______;
}
```
- 「型注釈を明示すること」は **ルール指示** であって答えではない
- 引数の型は使用例から判断、戻り値の型も挙動から判断
- 関数本体は完全に自力で書かせる

---

**学習目標: 配列の型注釈**

❌ 悪い faded:
```typescript
// scores という配列を number[] と明示的に型注釈する。中身は [80, 90, 100]。
const scores: ______ = [80, 90, 100];
```
- 答えそのもの（`number[]`）がコメントに

✅ 良い faded:
```typescript
// テストの点数を保持する配列 scores。型は明示的に書くこと。
const scores: ______ = [80, 90, 100];
//             ↑ 数値の配列。どう型注釈する？
```
- 「数値の配列」というのは **状況** であって型構文ではない
- ユーザーは `number[]` と `Array<number>` のどちらでも書けるが、選択責任がユーザー側に残る

### Faded の段階を設計する

1問の中で空欄の数を増減することで難度を調整する:

- **軽い faded**: 1-2 箇所だけ空欄。Stage 1 終盤〜Stage 2 序盤
- **中程度の faded**: 関数本体が空欄、シグネチャは見える。Stage 2 中盤
- **重い faded**: シグネチャと本体の構造だけ提示、ロジックは全部空欄。Stage 2 後半

重い faded まで到達したら、次は Open Problem（faded を卒業）に移行する。

### Faded で迷ったら自問する

問題を出す前に必ず:

1. **コメントから空欄の答えを取り除いても、課題の意図が伝わるか?** → 伝わらないなら、コメントが答えを言いすぎている
2. **ユーザーが空欄ごとに「考える」要素はあるか?** → ない箇所は埋めて出す
3. **写経でも空欄が埋まってしまうか?** → 埋まるならアウト、設計やり直し

## ヒント設計（3段階）

ユーザーが「ヒント」を要求した時、または `<details>` を展開した時の段階:

1. **誘導ヒント（軽）**: 着眼点・関連概念を提示
   - 例: 「`Array.prototype.length` の挙動を思い出してみてください」
2. **構造ヒント（中）**: 答えへの構造・手順を示唆
   - 例: 「2ステップで考えると、まず長さチェック、次にインデックスアクセス」
3. **具体ヒント（重）**: 答えに近い情報を出す
   - 例: 「`if (arr.length === 0)` から書き始めてください」

ヒント使用は **減点しない**（学習価値が下がるため）。ただし `Tags` 行に `hints_used: 2` のように記録し、レベル推定の参考にする。ヒント 2-3 段階を使って正解した場合、score は満点でもレベルアップは慎重に判断する。

## 出題のリズム（Interleaving と Spacing）

`references/curriculum-design.md` と整合させる:

### 単元導入直後（blocked）

新しい概念を導入したら、**同じ単元で 2-3問** 連続して出題する（Brunmair & Richter 2019）。これは習得促進フェーズ。

### 単元理解後（interleaved）

単元の正答率が 0.8+ で安定したら、**複数単元を混在出題** に切替。直近で学習した 3-4 単元から問題をローテーション。

### Spaced Reviews

過去の lesson を **目標保持期間の 10-15% の間隔** で復習問題として再出題。同じ問題ではなく、**同じ概念の別バリエーション** にする（recognition 防止）。

## セット出題（`format: set` の場合）

ユーザーがセット出題を選択した場合:

- 5問は **異なる Stage / 課題タイプ** から取る（多様性確保）
- 5問の難度プロファイルを混ぜる（直近正答率 70-85% を平均で狙う、5問単位で）
- ファイル末尾の回答欄を **5問分まとめて** 用意
- ユーザーが回答する前に答えや解説を出さない
- 全回答受領後、各問を順に採点 → 最後にまとめサマリ（合計平均、強弱の傾向、次の lesson の推奨方向）

## ファイル粒度の目安

1 lesson ファイル = **30-60分で取り組める単一の学習目標**。これより大きいと完了感が薄れ、小さいと文脈が断片化する。

例:
- ❌ 「TypeScript の型を学ぶ」（広すぎる、複数 lesson に分割すべき）
- ✅ 「Generic 関数を type parameter constraints 付きで書ける」（具体的、1 lesson）
