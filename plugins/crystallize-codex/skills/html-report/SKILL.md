---
name: html-report
description: >-
  「レポートにして」「HTMLレポート」で発動。散文の報告が30行を超えそうなときにも発動。
  長い報告を自己完結HTMLにして開く。
---

# html-report — 長い報告を自己完結HTMLで渡す

## Codex 実行境界

最初に `../../references/codex-runtime.md` を全文読む。このスキルは独立コンテキストでだけ実行する。入力に `CRYSTALLIZE_CODEX_ROLE=html-report` マーカーが無ければ、履歴を渡さない新規サブエージェントを起動し、同マーカー、この SKILL.md の絶対パス、素材の絶対パスまたは scoped_payload、output_contract を渡す。子の完了後、親は生成HTMLを確認してCodex内で表示する。独立実行を利用できない場合は同一コンテキストへフォールバックせず停止する。

あなたは独立サブエージェントとして動くレポート整形係。渡された素材を、**作業を見ていなかった読者**が最短で理解できる単一HTMLに整形する。チャットに長文を書く代わりに、このレポートが読まれる。

構成も部品も図も、このスキルが正本を持っている。**見た目を毎回ゼロから描かず、正本にある部品を選んで並べる** — 規則がこれだけ多いのはそのためで、見せ方を毎回考えると、同じ種類の報告がセッションごとに別物の見た目で出てくる。

## Input / Output

- **Input**: `起動メッセージまたは委任メッセージ` = 素材ファイルの絶対パス(推奨)またはインライン素材。任意指定: `type:`(research / compare / diff / loop)、`title:`
- **Output**: `<projroot>/docs/crystallize/reports/YYYY-MM-DD-<slug>.html` を生成し、親がCodex内のファイルまたはブラウザプレビューで表示する。最終応答は「結論の要約(3行以内)+生成ファイルのパス」のみ

## 最重要ルール(理由つき)

- **外部CDN・外部フォント・外部画像を参照しない** — オフラインや別マシンで開いた瞬間に壊れる。CSS/JS/図はすべてインライン(SVG直書き・base64)
- **素材にない事実を足さない・数値を丸めない** — レポートは目視確認の代替物。脚色が混ざると確認手段として死ぬ。不明な点は「素材に記載なし」と明示する
- **削って短くせず、畳んで短く見せる** — 詳細はタブ・`<details class="fold">` に格納する。用語は初出で一言補足し、本文は平易な完全文で書く
- **部品を即興で作らない** — 見た目の正本は `assets/style.css` と `assets/component-samples.html`。ここに無い見た目が要ると感じたら、その場で CSS を書かず、style.css への追記として最終応答で提案する(正本の外に生まれた部品は次の生成で消え、レポートごとに見た目が揺れる原因になる)
- **チャットにHTMLの中身を貼らない** — 親コンテキストの温存がこのスキルの存在理由
- **外部サービスへアップロードしない** — レポートはローカル生成して Codex内でプレビューするのが既定。アップロードはユーザーが明示的に頼んだ場合のみ

## Step 1: 入力解析

`起動メッセージまたは委任メッセージ` からファイルパス / type / title を抽出し、パスがあれば読む。type 未指定なら素材から推定する:

| 素材の特徴 | type |
|---|---|
| 反復採点の eval JSON 群 (score / passed の履歴) | loop |
| diff / patch / コミット・PRの変更説明 | diff |
| 複数案の比較・技術選定・トレードオフ | compare |
| それ以外(調査・研究・実装計画・障害報告) | research |

推定に迷ったら research。素材が空・不足しているときは、無いなりに作らず「不足している素材」を1行で呼び出し元へ返して終了する。

## Step 2: 生成前に必ず読む(3ファイル)

書き始める前に次を読む。**読まずに書き始めない** — 部品の見た目と図の座標は文章では伝わらず、思い出しで書くと必ず前回と違うものになる。

| ファイル | 何のために読むか |
|---|---|
| `<skill-dir>/assets/component-samples.html` | 全部品の実物と class 名。使ってよい部品はここにあるものだけ |
| `<skill-dir>/references/diagrams.md` | 「見せたいもの → 図の型」の対応表と、5種のSVGテンプレの座標 |
| `<skill-dir>/assets/style.css` | `<style>` に丸ごとインライン化する土台。変数名を目で確認する(推測で `--fg` 等と書かない) |

マークアップの骨格・タブ・diff テーブル・ファイルナビJSは `<skill-dir>/references/templates.md`。**`<skill-dir>` = この SKILL.md の絶対パスから解決したスキルディレクトリ**。同梱ファイルはこれを起点にした絶対パスで読む — 子の cwd は呼び出し元と一致する保証がなく、相対パスでは見つからない。Claude固有の変数は使わず、渡された絶対パスを使う。

## Step 3: 固定構成

type によらず、この順で並べる。**節を増やさない・順番を変えない** — 読者は毎回同じ場所を見れば同じ種類の情報が見つかる状態を期待する。

| # | 節 | 中身 |
|---|---|---|
| 1 | 要点 | `<div class="keypoints">` に3行以内。見出しは書かない(「要点」ラベルはCSSが付ける) |
| 2 | 用語 | `<dl class="terms">` にタスク固有の語だけ。無ければ節ごと省く(一般的な技術用語は書かない)。プロジェクトに用語集(リポジトリ直下に `## 用語` か `## Language` を持つ `CONTEXT.md` があればそれ、無ければ `docs/crystallize/CONTEXT.md`。どちらも無ければ spec の用語節)があれば**定義はそこから引き、このレポートで初出の語だけ**を載せる — 用語集と違う意味で語を使わない(レポート側に別の定義を作ると、読者はどちらが正かを判断できない) |
| 3 | 本論 | type 別に部品を選ぶ(Step 4)。h2 は目次と1対1 |
| 4 | 詳細 | `<details class="fold">` に畳む。全文・ログ・長い引用 |
| 5 | 根拠・出典 | ファイルパス・URL・素材のどこを見たか |

- 目次は `<nav class="report-toc">`。**番号を手で書かない** — CSS counter が `01`, `02` … を振る。`<main>` に `report-numbered` を付けると本文の h2 にも同じ番号が入る
- **見出しに絵文字を付けない** — 走査の目印は自動採番。絵文字は環境によって描画が揺れ、読み上げとページ内検索の役に立たない
- **`h2` は `.pane`(タブの中身)の外に置く。タブの中は `h3` 以下にする** — 非表示のペイン内の `h2` は採番されず、本文と目次の番号がずれる
- h1 直下に1文の `<p class="lede">` を置いてよい(このレポートが何の報告かの1行)

## Step 4: 本論の部品選択(type 別)

type で変わるのは**この節の部品だけ**。他の節は共通。

| type | 本論に置く部品 |
|---|---|
| research | 本文 + 必要なら図。長い節はタブ(`.tabs`/`.pane`)で 概要 / 詳細 / 根拠 に分ける |
| compare | 比較グリッド(`.cards` > `.card` + `.badge`)→ トレードオフ表 → 案ごとの詳細タブ |
| diff | 変更サマリ表 → `details.file` + `.diff-table`(構造は templates.md のまま) |
| loop | スコア推移の折れ線(diagrams.md 付録)→ criteria 別の推移 → iteration ごとの feedback を `details.fold` に |

<important if="type が loop (反復採点ダッシュボード)">
- 素材は「iteration ごとの eval JSON 群」(question-evaluator が書く schema と同形: `score` / `quality.breakdown` / `passed`)。ファイルを iteration 順に読み、時系列化する
- 閾値 (threshold) が素材にあれば閾値線と現在地を描く
- `quality.breakdown` のキーは全 iteration で固定 — キーごとに折れ線を引くと、どの基準が収束せず足を引っ張っているかが一目でわかる
</important>

## 色・表・図の規則(理由つき)

- **有彩色は primary 1色 + 警告 1色(`--warn`)だけ** — 色数が増えると、色そのものが意味を運ばなくなる。例外は機能色としての diff の緑赤と、diff-review の承認済み表示(同じ緑を状態色として流用する)の2つ
- **強調(`.emph`)は 1ページ 1箇所** — 2箇所目を足した時点でどちらも目立たなくなる。2箇所目が要るなら、それは強調ではなく節を分けるべき内容
- **表は3列まで。セルに文を書かない** — 4列目からは横に読めなくなる。文が要る内容は表ではなくカードか箇条書きにする
- **表の行見出し列には `class="rowhead"`** を付ける(折り返し禁止)
- **図は `references/diagrams.md` の5種から選ぶ**。型が決まらないものは図にしない。図は必ず `<figure class="figure">` で包み、**それを支える文の直後**に置く
- **図中の語は本文の語と一致させる** — 図の中で新語を導入すると、読者に照合する手段がない

## Step 5: 保存と表示

```bash
PROJROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
mkdir -p "$PROJROOT/docs/crystallize/reports"
# YYYY-MM-DD-<slug>.html をファイル編集ツールで作る
# 親がCodex内で表示する
```

`docs/crystallize/reports/` がそのプロジェクトの .gitignore に無い場合は、最終応答に「gitignore 未設定」と一言添える(勝手に .gitignore を編集しない — 整形係が対象リポジトリを変更すると作業diffが汚れる)。

## Step 6: 最終応答

結論の要約(3行以内)+ファイルパス+(あれば)gitignore注意+(あれば)style.css への部品追加の提案のみを返す。呼び出し元はこれをそのままユーザーに中継する。

## Gotchas

- チャート描画に Chart.js 等を使いたくなるが CDN 禁止 — 折れ線はインライン SVG の `<polyline>` で十分描ける(diagrams.md 付録)
- SVG の日本語ラベルが箱から溢れるのは SVG のせいではなく幅を見積もっていないから — diagrams.md の幅の式(全角1.0em / 半角0.6em)で計算してから置く。溢れるのが怖いという理由で図を CSS の div に置き換えない(見た目が別物になった実績がある)
- 1ページに図を複数置くとき、SVG の `marker` の `id` が重複すると**最初の定義だけが黙って使われる** — id は figure ごとに固有にする
- ダークは `html[data-theme="dark"]` でのみ切り替わる(`prefers-color-scheme` を直接見ているのは初期値の決定だけ) — テーマ切替ボタンと初期化JSは templates.md の骨格に入っている。自前で書き直さない
- 素材パスは絶対パスで受ける前提。相対パスで見失ったら、推測で探し回らず「不足」として返す — 子の cwd は呼び出し元と一致する保証がない
- 巨大 diff(数千行)を全部埋め込むと HTML が数MBになる — ファイル別タブ+ブロック単位の `<details>` で畳む(省略はしない)
- Codex内の表示に失敗しても生成失敗にはしない — クリック可能な絶対パスを返して呼び出し元が対処できる

## Additional resources

- `assets/component-samples.html` — **全部品を1枚に並べた見本(見た目の正本)**。生成前に必ず読む。単体でブラウザで開ける
- `assets/style.css` — 土台スタイル + 部品CSSの正本。CSS変数でライト/ダークを管理
- `references/diagrams.md` — 図解カタログ(「見せたいもの → 図の型」の対応表、5種のSVGテンプレ、loop の折れ線)
- `references/templates.md` — HTML骨格(テーマ切替つき)、タブJS、diff テーブル、ファイルナビJS
- `references/notion-design.md` — style.css のデザイントークン出典(Notion デザイン分析)

component-samples.html に埋め込んだ CSS は style.css の全文コピー。style.css を変更したら貼り直す。同期の検算(**レポート生成時ではなく、プラグインリポジトリで正本を編集したときに走らせる保守用コマンド**):

```bash
cd <プラグインリポジトリ>/plugins/crystallize/skills/html-report
sed -n '/<style>/,/<\/style>/p' assets/component-samples.html | sed '1d;$d' > "${TMPDIR:-/tmp}/inlined.css"
diff "${TMPDIR:-/tmp}/inlined.css" assets/style.css   # 差分なしが正
```
