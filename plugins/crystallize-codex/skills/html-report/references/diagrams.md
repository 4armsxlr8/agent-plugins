# html-report — 図解カタログ (インライン SVG)

レポートに入れる図の**唯一の正本**。図は 5 種に固定し、テンプレの座標と class は無改変で使い、差し替えるのはラベル文字列とノード数だけにする。

なぜ固定するか: 図は毎回ゼロから描かれると、同じ「手順の流れ」がレポートごとに横フロー・箱の羅列・CSS の div 積み上げに化ける。実際、直近の生成物では「SVG は日本語が溢れる」という理由で図が CSS ボックスに置き換わり、図の体裁だけが別物になった。溢れるのは幅の見積もりがないからで、SVG が悪いのではない。本ファイルは幅の計算式まで含めて固定する。

Mermaid は使わない — ローカル HTML では CDN なしに描画できず、CDN 禁止の最重要ルールと衝突する。

## 見せたいもの → 図の型

| 見せたいもの | 型 | テンプレ |
|---|---|---|
| 手順・因果の連なり (分岐や合流がある) | 縦フロー | §1 |
| 案 × 評価軸の当たり外れを面で見せる | 比較マトリクス | §2 |
| 変更前と変更後の対応 | before-after 並置 | §3 |
| 構造・責務の階層、浅いファイル構成 | ツリー | §4 |
| 時系列・経緯・予定 | タイムライン | §5 |
| 反復採点のスコア推移 (type: loop) | 折れ線 | 付録 |
| 単なる直列手順 (分岐も対応関係もない) | **図にしない** — 番号付き箇条書き | — |
| 数値の大小をそのまま比べる | **図にしない** — 3 列までの表 | — |

**5 種すべてを使おうとしない。** 今の論点に必要な型だけ使う。型が決まらない figure は、たいてい図にする必要がない。

## 図の使い方の規則 (理由つき)

- **図はそれを支える文の直後に置く** — 図が先に来ると、読者は図を解読してから文で答え合わせをすることになり、同じ内容を二度読む
- **図中の語は本文の語と一致させ、図の中で新語を導入しない** — 図で初出の語は用語節にも本文にもなく、読者が照合できない。語を短くしたいなら本文側も短くする
- **ノードが 5 を超えたら縦に並べる** — 横に並べるとラベル幅が足りなくなる。日本語は縮めると読めない
- **矢印を交差させない** — 交差が 1 本入るだけで、読者は線を目で追う作業を強いられる。交差するなら並び順のほうが間違っている
- **絵文字・矢印文字 (→ ⇒ ▶ ✅) を図記号に使わない** — フォント依存で描画が揺れ、拡大すると崩れ、読み上げでも意味を持たない。方向は marker の三角形、状態は色と枠線で示す
- **強調は 1 図に 1 系統** — `dg-node-em` (primary) か `dg-node-warn` (警告) のどちらか。両方使うと、どちらが重いのか読めなくなる
- **図の外は figure、説明は figcaption** — 図の読み方 (色が何を意味するか等) は figcaption に書く。本文に混ぜると図から離れる

## 共通の書き方 (全テンプレ共通・無改変層)

### 器

```html
<figure class="figure">
  <svg viewBox="0 0 {W} {H}" style="max-width:{W}px" role="img" aria-label="{図の要約 1 文}">
    …
  </svg>
  <figcaption>{図の読み方。色や記号の意味があればここに書く}</figcaption>
</figure>
```

- `style="max-width:{W}px"` は必ず付ける — 付けないと横幅の広い画面で図だけ拡大され、文字が間延びする。`.figure > svg` 側で `width:100%; height:auto` は指定済み
- `role="img"` と `aria-label` も必ず付ける — 図の中の `<text>` は読み上げでは断片としてしか読まれないため、図全体の要約を 1 文で持たせる
- 色・線・文字色は `assets/style.css` の `dg-*` class だけで指定する。SVG の presentation 属性に hex を書かない — ダーク側だけ見えなくなる

### 使える描画 class (これで全部)

| class | 用途 |
|---|---|
| `dg-node` / `dg-node-em` / `dg-node-warn` | 箱。既定 / 強調 (primary) / 警告 |
| `dg-band` | 背景の帯・グループ枠 |
| `dg-line` / `dg-line-em` / `dg-line-dash` | 線。既定 / 強調 / 補助線 (閾値など) |
| `dg-arrow` / `dg-arrow-em` | marker の三角形 |
| `dg-dot` / `dg-dot-em` | 点 |
| `dg-label` (13px) / `dg-sub` (11px) / `dg-title` (12px) / `dg-mono` (11px 等幅) | 文字 |

### 矢印の marker

```html
<defs>
  <marker id="{figId}-arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 Z" class="dg-arrow"/>
  </marker>
</defs>
```

- **`id` は必ず figure ごとに固有にする** (`{figId}` = 図ごとの短い接頭辞)。1 ページに複数の図を置くと id が重複し、**最初の定義だけが黙って使われる** — 壊れずに間違うので気づけない
- 参照は `marker-end="url(#{figId}-arrow)"`

### 日本語ラベルの幅 (溢れの原因はここ)

`.dg-label` は 13px。文字の実幅はおおよそ次で見積もる。

```
幅(px) = font-size × (全角の文字数 + 0.6 × 半角の文字数)
```

- 全角 (かな・漢字・全角記号) = 1.0em、半角英数・空白 = 約 0.6em
- 中央寄せの箱に入れる条件: `幅 + 24 ≤ 箱の幅` (左右パディング 12px ずつ)
- 例: 「P4 挙動ゲート」= 全角 6 + 半角 3 → 13 × (6 + 1.8) = 101px。420px の箱に余裕で入る
- 超えるときの順番: **(1) 語を短くする → (2) `dg-sub` の 2 行目に逃がす → (3) それでも無理ならノードを分ける**。箱を広げるのは最後 (他の箱と幅が揃わなくなる)

2 行にするとき:

```html
<text class="dg-label" x="{cx}" y="{cy}" text-anchor="middle">
  <tspan x="{cx}" dy="-0.15em">1 行目</tspan>
  <tspan x="{cx}" dy="1.35em">2 行目</tspan>
</text>
```

- 縦位置は `dominant-baseline` ではなく `dy=".35em"` で合わせる — 環境差が出にくい

---

## 1. 縦フロー

手順・因果の連なりを上から下へ。分岐・合流があるときに使う (無いなら箇条書き)。

**座標** (W = 560 固定、ノード数 n)

| 値 | 式 |
|---|---|
| ノード i の上端 y | `y(i) = 20 + 72i` |
| 全体の高さ H | `H = 12 + 72n` |
| 箱 | `x=70 w=420 h=44 rx=8` |
| ラベル中心 | `x=280, y=y(i)+22` (`dy=".35em"`) |
| 2 行目 (`dg-sub`) を出すとき | ラベル `y(i)+18` / sub `y(i)+34` |
| 矢印 | `x=280` を `y(i)+44` から `y(i)+69` へ |

```html
<figure class="figure">
  <svg viewBox="0 0 560 300" style="max-width:560px" role="img" aria-label="{要約}">
    <defs>
      <marker id="{figId}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="dg-arrow"/>
      </marker>
    </defs>
    <!-- 繰り返し: ノード (i = 0,1,2,… / 最後のノードは矢印を出さない) -->
    <rect class="dg-node" x="70" y="20" width="420" height="44" rx="8"/>
    <text class="dg-label" x="280" y="42" dy=".35em" text-anchor="middle">{ラベル}</text>
    <line class="dg-line" x1="280" y1="64" x2="280" y2="89" marker-end="url(#{figId}-arrow)"/>
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>{読み方}</figcaption>
</figure>
```

- 矢印に条件を添えるなら `<text class="dg-sub" x="292" y="{y(i)+60}">{条件}</text>` (矢印の右)
- 強調するノードは `dg-node` を `dg-node-em` に替えるだけ。位置は変えない

## 2. 比較マトリクス

案 (列) × 評価軸 (行) の当たり外れを面で見せる。**セルに文を書けるなら表にする** — この図が要るのは「どの案がどの軸で強いか」を面で掴ませたいときだけ。

**座標** (行 m ≤ 5、列 n ≤ 3)

| 値 | 式 |
|---|---|
| 全体の幅 W | `W = 170 + 130n` (n=3 で 560) |
| 全体の高さ H | `H = 66 + 44m` |
| 列見出し | `x = 211 + 130j, y = 38` (`dg-title`, 中央) |
| セル矩形 | `x = 150 + 130j, y = 52 + 44i, w = 122, h = 38, rx = 6` |
| セル文字 | `x = 211 + 130j, y = 71 + 44i` (`dy=".35em"`, 中央) |
| 行見出し | `x = 20, y = 71 + 44i` (`dg-label`, 左寄せ) |

```html
<figure class="figure">
  <svg viewBox="0 0 560 242" style="max-width:560px" role="img" aria-label="{要約}">
    <!-- 繰り返し: 列見出し (j = 0,1,2) -->
    <text class="dg-title" x="211" y="38" text-anchor="middle">{案名}</text>
    <!-- 繰り返し終わり -->
    <!-- 繰り返し: 行 (i = 0,1,…) -->
    <text class="dg-label" x="20" y="71" dy=".35em">{評価軸}</text>
    <!-- 繰り返し: セル (j = 0,1,2 / 当たりのセルだけ dg-node-em) -->
    <rect class="dg-node" x="150" y="52" width="122" height="38" rx="6"/>
    <text class="dg-label" x="211" y="71" dy=".35em" text-anchor="middle">{短い語}</text>
    <!-- 繰り返し終わり -->
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>{読み方。色が何を意味するかをここに書く}</figcaption>
</figure>
```

- セルの語は全角 8 文字まで (122px 幅)。入らない語は表側で短くする
- 記号 (◎○△) だけにしない — 理由が読めないと判断材料にならない。短い語にする

## 3. before-after 並置

変更前と変更後を左右に並べ、**変わる箇所だけ**を `dg-node-em` にする。

**座標** (W = 640 固定、片側のノード数 n)

| 値 | 式 |
|---|---|
| 全体の高さ H | `H = 56 + 54n` |
| 列見出し | 左 `x=20` / 右 `x=350`, `y=30` (`dg-title`, 左寄せ) |
| 箱 | 左 `x=20` / 右 `x=350`, `y = 46 + 54i`, `w=270 h=44 rx=8` |
| ラベル | 箱の `x+12`, `y = 46+54i+24` (左寄せ)。2 行なら `+18` と `+34` |
| 中央の矢印 | `y = H/2` を `x=296` から `x=344` へ |

```html
<figure class="figure">
  <svg viewBox="0 0 640 326" style="max-width:640px" role="img" aria-label="{要約}">
    <defs>
      <marker id="{figId}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="dg-arrow"/>
      </marker>
    </defs>
    <text class="dg-title" x="20" y="30">BEFORE</text>
    <text class="dg-title" x="350" y="30">AFTER</text>
    <line class="dg-line" x1="296" y1="163" x2="344" y2="163" marker-end="url(#{figId}-arrow)"/>
    <!-- 繰り返し: 左の行 (i = 0,1,…) -->
    <rect class="dg-node" x="20" y="46" width="270" height="44" rx="8"/>
    <text class="dg-label" x="32" y="70" dy=".35em">{変更前}</text>
    <!-- 繰り返し終わり -->
    <!-- 繰り返し: 右の行 (変わる行だけ dg-node-em) -->
    <rect class="dg-node-em" x="350" y="46" width="270" height="44" rx="8"/>
    <text class="dg-label" x="362" y="70" dy=".35em">{変更後}</text>
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>色付き = 今回変わる箇所。{その他の読み方}</figcaption>
</figure>
```

- 左右の行数を揃える。片側にしか無い行は、もう片側に「なし」の箱を置く — 行がずれると対応関係が読めなくなる
- ラベルは 270px 幅 = 全角 18 文字まで

## 4. ツリー

構造・責務の階層、浅いファイル構成。箱を使わず、エルボー線 + 左寄せの文字で描く — 日本語ラベルは長さがまちまちで、箱に入れると幅が揃わないため。

**座標** (行数 n。**W は固定しない** — 中身に合わせて詰める)

| 値 | 式 |
|---|---|
| 全体の幅 W | `W = 最も右まで伸びる行の終端 + 20` (§共通の幅の式で見積もる) |
| 全体の高さ H | `H = 30n + 20` |
| 深さ d のラベル開始 x | `X(d) = 30 + 30d` |
| 行 i の中心 y | `Y(i) = 30 + 30i` |
| 縦線 (親 p → 子 i) | `x = X(d-1) + 4` を `Y(p) + 10` から `Y(i)` へ |
| 横線 | `x = X(d-1) + 4` から `X(d) - 6` へ、`y = Y(i)` |

W を 560 のような固定値にしない — 中身が左寄せなので、右に余白が残ると図全体が左に寄って見える (`.figure > svg` は中央寄せのため)。

```html
<figure class="figure">
  <svg viewBox="0 0 330 290" style="max-width:330px" role="img" aria-label="{要約}">
    <!-- 根 (深さ 0) -->
    <text class="dg-label" x="30" y="30" dy=".35em">{根のラベル}</text>
    <!-- 繰り返し: 子ノード (深さ d ≥ 1 / 縦線・横線・ラベルの 3 行で 1 ノード) -->
    <line class="dg-line" x1="34" y1="40" x2="34" y2="60"/>
    <line class="dg-line" x1="34" y1="60" x2="54" y2="60"/>
    <text class="dg-label" x="60" y="60" dy=".35em">{ラベル}<tspan class="dg-sub" dx="8">{補足}</tspan></text>
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>{読み方}</figcaption>
</figure>
```

- 同じ親の子が複数あるとき、縦線は**最後の子まで 1 本**にまとめてよい (`Y(p)+10` から最後の子の `Y(i)` まで 1 本 + 子ごとに横線)。線が増えるより読みやすい
- 深さは 3 まで。4 段目が要るなら、その部分木を別の図に分ける — 30px 刻みの字下げでは 4 段目のラベル幅が足りなくなる
- パスやコード識別子は `class="dg-mono"` の `tspan` にする

## 5. タイムライン

時系列・経緯・予定。**縦のレール**で描く — 横軸に日本語ラベルを並べると隣と重なる。

**座標** (出来事の数 n。ツリーと同じく **W は固定しない**)

| 値 | 式 |
|---|---|
| 全体の幅 W | `W = 最も長い見出しまたは補足の終端 + 20` |
| 全体の高さ H | `H = 52n + 20` |
| レール | `x=96`, `y=26` から `H-14` へ (時間の向きを示すため矢印を付ける) |
| 出来事 i の y | `y(i) = 36 + 52i` |
| 点 | `cx=96, cy=y(i), r=5` |
| 日付 (`dg-mono`) | `x=80, y=y(i)`, 右寄せ |
| 見出し (`dg-label`) | `x=114, y=y(i)`, 左寄せ |
| 補足 (`dg-sub`) | `x=114, y=y(i)+17` |

```html
<figure class="figure">
  <svg viewBox="0 0 346 228" style="max-width:346px" role="img" aria-label="{要約}">
    <defs>
      <marker id="{figId}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 Z" class="dg-arrow"/>
      </marker>
    </defs>
    <line class="dg-line" x1="96" y1="26" x2="96" y2="214" marker-end="url(#{figId}-arrow)"/>
    <!-- 繰り返し: 出来事 (現在地・転機だけ dg-dot-em) -->
    <circle class="dg-dot" cx="96" cy="36" r="5"/>
    <text class="dg-mono" x="80" y="36" dy=".35em" text-anchor="end">{日付}</text>
    <text class="dg-label" x="114" y="36" dy=".35em">{出来事}</text>
    <text class="dg-sub" x="114" y="53">{補足}</text>
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>{読み方}</figcaption>
</figure>
```

- 日付は等幅 (`dg-mono`) で桁を揃える。表記は全出来事で統一する (`2026-09-04` と `9/4` を混ぜない)
- 見出しは 1 行に収める。長くなるなら W を広げるのではなく語を短くする — W は最も長い行に合わせるので、1 行だけ極端に長いと図全体が横に伸び、他の行が間延びして見える

---

## 付録: スコア推移の折れ線 (type: loop 専用)

反復採点ダッシュボード用。5 種の図とは別枠で、`quality.breakdown` の推移を見るためだけに使う。

**座標** (W = 640, H = 240 固定、iteration 数 N)

| 値 | 式 |
|---|---|
| 点 i の x | `x = 40 + i × (600 - 40) / max(N-1, 1)` |
| 点 i の y | `y = 220 - (score / 100) × 200` |
| 閾値線の y | `yThr = 220 - (threshold / 100) × 200` |

```html
<figure class="figure">
  <svg viewBox="0 0 640 240" style="max-width:640px" role="img" aria-label="スコア推移">
    <line class="dg-line" x1="40" y1="220" x2="620" y2="220"/>
    <line class="dg-line-dash" x1="40" y1="{yThr}" x2="620" y2="{yThr}"/>
    <text class="dg-sub" x="40" y="{yThr - 8}">閾値 {threshold}</text>
    <polyline class="dg-line-em" points="{x1},{y1} {x2},{y2} …"/>
    <!-- 繰り返し: 点 (passed の回だけ dg-dot-em) -->
    <circle class="dg-dot" cx="{x}" cy="{y}" r="4"/>
    <text class="dg-sub" x="{x}" y="{y-10}" text-anchor="middle">{score}</text>
    <!-- 繰り返し終わり -->
  </svg>
  <figcaption>{読み方。閾値と、どの基準が収束していないか}</figcaption>
</figure>
```

- iteration が 1 つだけなら `polyline` を出さず `circle` だけにする
- criteria 別の推移は、同じ SVG に細線で重ねるか、breakdown のキーごとに小さな SVG を並べる。キーは全 iteration で固定なので、キーの並び順も固定する
- 素材の集計は次で足りる:

```bash
# EVAL_DIR = iteration ごとの eval JSON が並ぶディレクトリ (ファイル名は iteration 順に整列すること)
for f in "$EVAL_DIR"/*-eval.json; do
  jq -c '{score, passed, breakdown: .quality.breakdown}' "$f"
done
```

## 検算 (図を出す前に必ず通す)

1. `viewBox` の `H` が式どおりか (ノード数を変えたら H も変わる)
2. `marker` の `id` がページ内で一意か
3. ラベルの見積もり幅 + 24 が箱の幅以内か (§共通の計算式)
4. 色を SVG 属性に直書きしていないか (`fill="#` / `stroke="#` を grep する)
5. `viewBox` の右と下に余白が残っていないか (中身が左寄せの図は、余白のぶん左に寄って見える)
6. `role="img"` と `aria-label` があるか
