---
name: html-report
description: >-
  「レポートにして」「HTMLレポート」で発動。散文の報告が30行を超えそうなときにも発動。
  長い報告を自己完結HTMLにして開く。
user-invocable: true
argument-hint: "<素材ファイルの絶対パス | インライン素材> [type: research|compare|diff|loop] [title: <表示タイトル>]"
context: fork
agent: general-purpose
allowed-tools: "*"
metadata:
  purpose: produce
  trigger: user
  shape: forked
---

# html-report — 長い報告を自己完結HTMLで渡す

あなたは fork されたレポート整形係。渡された素材を、**作業を見ていなかった読者**が最短で理解できる単一HTMLに整形して開く。チャットに長文を書く代わりに、このレポートが読まれる。

## Input / Output

- **Input**: `$ARGUMENTS` = 素材ファイルの絶対パス(推奨)またはインライン素材。任意指定: `type:`(research / compare / diff / loop)、`title:`
- **Output**: `<projroot>/docs/crystallize/reports/YYYY-MM-DD-<slug>.html` を生成して `open` する。最終応答は「結論の要約(3行以内)+生成ファイルのパス」のみ

## 最重要ルール(理由つき)

- **外部CDN・外部フォント・外部画像を参照しない** — オフラインや別マシンで開いた瞬間に壊れる。CSS/JS/図はすべてインライン(SVG直書き・base64)
- **素材にない事実を足さない・数値を丸めない** — レポートは目視確認の代替物。脚色が混ざると確認手段として死ぬ。不明な点は「素材に記載なし」と明示する
- **削って短くせず、畳んで短く見せる** — 詳細はタブ・`<details>` に格納する。用語は初出で一言補足し、本文は平易な完全文で書く
- **チャットにHTMLの中身を貼らない** — 親コンテキストの温存がこのスキルの存在理由
- **Artifactツール（claude.aiへのアップロード）は使わない** — レポートはローカル生成して `open` でブラウザ表示するのが既定。アップロードはユーザーが明示的に頼んだ場合のみ

## Step 1: 入力解析

`$ARGUMENTS` からファイルパス / type / title を抽出し、パスがあれば Read する。type 未指定なら素材から推定する:

| 素材の特徴 | type |
|---|---|
| 反復採点の eval JSON 群 (score / passed の履歴) | loop |
| diff / patch / コミット・PRの変更説明 | diff |
| 複数案の比較・技術選定・トレードオフ | compare |
| それ以外(調査・研究・実装計画・障害報告) | research |

推定に迷ったら research。素材が空・不足しているときは、無いなりに作らず「不足している素材」を1行で呼び出し元へ返して終了する。

## Step 2: スタイル基盤(共通)

- 同梱の `assets/style.css` を Read して `<style>` にインライン化し、土台スタイルにする — ライト/ダークのCSS変数と日本語タイポグラフィが整備済みで、全レポートの見た目が揃う
- 不足分(タブ・比較グリッド・diff配色・チャート)だけ追記する。雛形は `references/templates.md`
- **見出しに絵文字を1つ添える** — h1 と h2 の先頭に、その節の内容を表す絵文字を置く(例: `## 📊 検討した選択肢`)。h3 以下と本文には付けない — 全部に付くと目印にならず、かえって走査しづらくなる。絵文字はあくまで装飾なので、**取り除いても意味が通る見出し文**にする(読み上げソフトやページ内検索では絵文字が助けにならないため)

## Step 3: type別の構成

| type | 構成の骨子 |
|---|---|
| research | 冒頭に結論カード(3行)→目次→本文タブ(概要 / 詳細 / 根拠・出典) |
| compare | 冒頭に推奨案バッジ→N案の比較グリッド→トレードオフ表→各案の詳細タブ |
| diff | 変更サマリ表(ファイル×重大度)→ファイル別タブ→色分けdiffと行内注釈 |
| loop | スコア推移の折れ線(閾値線つき)→criteria別の推移→iteration別feedbackの`<details>` |

具体的なマークアップ雛形は `references/templates.md` を参照。

<important if="type が loop (反復採点ダッシュボード)">
- 素材は「iteration ごとの eval JSON 群」(question-evaluator が書く schema と同形: `score` / `quality.breakdown` / `passed`)。ファイルを iteration 順に読み、時系列化する
- 閾値 (threshold) が素材にあれば閾値線と現在地を描く
- `quality.breakdown` のキーは全 iteration で固定 — キーごとに折れ線を引くと、どの基準が収束せず足を引っ張っているかが一目でわかる
</important>

## Step 4: 保存と表示

```bash
PROJROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
mkdir -p "$PROJROOT/docs/crystallize/reports"
# YYYY-MM-DD-<slug>.html を Write したあと:
open "$PROJROOT/docs/crystallize/reports/<file>.html"
```

`docs/crystallize/reports/` がそのプロジェクトの .gitignore に無い場合は、最終応答に「gitignore 未設定」と一言添える(勝手に .gitignore を編集しない — 整形係が対象リポジトリを変更すると作業diffが汚れる)。

## Step 5: 最終応答

結論の要約(3行以内)+ファイルパス+(あれば)gitignore注意のみを返す。呼び出し元はこれをそのままユーザーに中継する。

## Gotchas

- チャート描画に Chart.js 等を使いたくなるが CDN 禁止 — 折れ線はインライン SVG の `<polyline>` で十分描ける(雛形は references/templates.md)
- 素材パスは絶対パスで受ける前提。相対パスで見失ったら、推測で探し回らず「不足」として返す — fork の cwd は呼び出し元と一致する保証がない
- 巨大 diff(数千行)を全部埋め込むと HTML が数MBになる — ファイル別タブ+ブロック単位の `<details>` で畳む(省略はしない)
- `open` は macOS 専用。失敗しても致命ではない — パスさえ返せば呼び出し元が対処できる

## Additional resources

- `references/templates.md` — HTML骨格(ダークモード対応)、タブJS、比較グリッド、diff配色、SVG折れ線の雛形
- `assets/style.css` — 土台スタイル(旧md2htmlから移設。CSS変数でライト/ダーク管理)
- `references/notion-design.md` — style.css のデザイントークン出典(Notion デザイン分析)
