# diff-review 固有コンポーネント — 正本仕様

diff-review のレポートで使う **diff-review 固有部品の唯一の正本**。ページ骨格・タブ・diff テーブル・ファイルナビは派生元 `../../html-report/references/templates.md` と `../../html-report/assets/style.css` が正本であり、本ファイルは**その上に足す部品だけ**を定義する (基盤側の構造を再掲しない — 同じ要素の正本が2つあると必ず乖離する)。

**diff-review の `<main>` は `class="report report-numbered"` とし、`markdown-body` を付けない** — `.markdown-body table` のような子孫セレクタ (詳細度 (0,1,1)) が本ファイルの固有部品の単一 class (0,1,0) に勝ち、無改変層で貼ったはずの見た目 (グループ集計表・決裁カードの dl・diff テーブル) が上書きされる。

## なぜ正本を固定するか

バッジ・ヘッダ集計・承認チェック・保存 JS は従来 SKILL.md の散文指示だけで定義されており、生成のたびに fork がマークアップ・CSS・JS を即興で発明していた。散文は「何を作るか」は固定できても「どう見えるか」は固定できない。完全に書き下した部品 (templates.md のファイルナビ JS) が揺れなかった実績に合わせ、固有部品も全部品を書き下す。

## 契約 — 2層 (どこまで無改変か)

| 層 | 対象 | 扱い |
|---|---|---|
| **無改変層** | 本ファイルの `<style>` ブロックと `<script>` ブロック | 一字も変えずにレポートへ貼る |
| **スロット層** | 本ファイルのマークアップ雛形 | 骨格は無改変。`{…}` プレースホルダの中身と、`<!-- 繰り返し: … -->` コメント直下の行の反復回数**だけ**を差し替える。要素・class の追加削除・並べ替えはしない |

- プレースホルダ規約: `{title}` のような `{}` 単一値と、`<!-- 繰り返し: <単位> -->` の直下1ブロックを反復する2形式のみ
- 色は必ず style.css の CSS 変数経由。**新しい色・新しい class を発明しない**。部品が足りないと感じたら即興で足さず、本ファイルへの追記として提案する (正本の外に生まれた部品は次の生成で消える)

## 部品一覧 (この7つで全固有部品)

1. **ヘッダブロック** — タイトル、`N files / M hunks +a -d` 統計、要約行「人間が見るべき箇所 N 件 / 全 M hunk」、グループ集計表 (グループ名・タグ・リスク・hunk 数「うち昇格 n」・指摘)、承認プログレス「確認 0/N」
2. **受け入れ基準節** — 挙動ゲート通過済みの記録としての表示専用リスト (チェックさせない)。出所は spec の「受け入れ基準 (テストケース表)」、spec が無い旧形式なら plan の受け入れ基準節
3. **セクション見出し** — `01 昇格 (人間が見る)` / `02 非昇格 (畳み済み)` の2見出しと、02 のグループ単位の小見出し + 意図解説
4. **昇格理由バッジ** — 決裁カード (部品7) の見出し行に置く ①〜⑥ のバッジ (複数可)。**形は全種共通・色は2系統のみ**: ①② (不可逆・対外境界) = `--diff-del-bg` 地 + `--diff-del-fg` 字、③〜⑥ = `--primary-tint` 地 + `--primary` 字。番号 + 短ラベル (例: `① 不可逆`) で種別を運ぶ — 6色に塗り分けない (トークンに6色は無く、発明した色は揺れの再発源になる)
5. **承認チェック** — 昇格ファイルの `<details class="file">` **内の末尾**に置くチェックブロック (ラベルは「このリスクを受け入れる」の決裁)。`file-head` への状態バッジ (✓ 確認済み / 未確認) は **`.file-name` の直後に挿入**する (file-head 自体の構造は templates.md の正本のまま)。1 ファイルに決裁カードが複数あっても**チェックは 1 個**で、そのファイルの全カードを覆う (部品6 JS が `details.file` 単位で保存キーを作るため、粒度をファイルより細かくできない)。**昇格 0 件のときの単独チェックの variant は廃止した** — 昇格 0 件なら SKILL.md のスキップ規則で HTML 自体を作らないので、置かれる場面が存在しない
6. **承認 JS** — チェック変更で `details.file` に `.approved` を付け外しし、状態バッジ・ファイルナビ・ヘッダの「確認 n/N」カウンタへ反映、localStorage へ保存する。**templates.md のファイルナビ生成スクリプトより後に置く** (ナビ項目を装飾するため)。キーは `diff-review:` + レポートのファイル名 (`location.pathname` の basename)。**復元時はカウンタだけでなく `.approved`・状態バッジ・ナビ表示も再適用する**。チェック1件ごとのキーは `.file-name` の文字列 + そのファイル先頭の `.decision-locus` (**無改変層をここだけ改訂した**。以前は `details.file` の id を使っていたが、id は登場順の連番なので、同じ日に同じ slug で作り直したレポートに別ファイルの承認が復元されていた)
7. **決裁カード** — 昇格 hunk 1 件につき 1 枚。コードより先に平文 4 点 (何が起きうるか / 元に戻せるか / 影響範囲 / AI レビューの判定と根拠) を置き、diff 本体は `<details class="decision-diff">` に畳む (既定 closed)。人間に求めるのはリスクを受け入れるかどうかの決裁であって、コードが正しいかの判定ではない — 判定に要らないコードを既定で開いておくと、読む対象が決裁の材料からコードにすり替わる。4 点の見出し語は固定で言い換えない (毎回違う言葉になると、読み手がどこを見ればよいか毎回探し直す)

## class 命名

style.css の既存イディオムに合わせる (セマンティックな kebab-case、接頭辞なし — この部品はスキル自身のページ内で完結するため、tweak-panel のような防御接頭辞は不要)。**style.css / templates.md で定義済みの class 名と衝突しないこと** (追加前に grep で確認する)。

## テンプレート

<!-- TEMPLATE:BEGIN -->
```html
<!--
  diff-review 固有部品 — components.md の「テンプレート」節へそのまま埋め込む断片。
  無改変層: <style> と <script> は一字も変えずに貼る。
  スロット層: マークアップ雛形は {…} プレースホルダと繰り返しコメントの中身・反復回数だけ差し替える。
  部品1〜5・7は report-main (templates.md の .report-layout > .report-main) の中に置く。
-->

<!-- ═══ 部品1: ヘッダブロック ═══ -->
<header class="review-header">
  <h1 class="review-title">{title}</h1>
  <p class="review-stats">
    <span>{fileCount} files</span>
    <span>{hunkCount} hunks</span>
    <span class="stat-add">+{added}</span>
    <span class="stat-del">-{deleted}</span>
  </p>
  <p class="review-summary">人間が見るべき箇所 <strong>{escalatedHunkCount}</strong> 件 / 全 <strong>{hunkCount}</strong> hunk</p>

  <table class="group-table">
    <thead>
      <tr><th>グループ</th><th>タグ</th><th>リスク</th><th>hunk数</th><th>指摘</th></tr>
    </thead>
    <tbody>
      <!-- 繰り返し: グループ行 (Step2 の表と1対1対応) -->
      <tr>
        <td>{groupName}</td>
        <td><span class="group-tag">{tag}</span></td>
        <!-- risk-badge の class は risk-low / risk-caution / risk-warn の3種から1つ選ぶ (下は risk-caution の例) -->
        <td><span class="risk-badge risk-caution">{riskLabel}</span></td>
        <td>{hunkTotalInGroup}<span class="group-escalated">(うち昇格 {escalatedInGroup})</span></td>
        <td>{note}</td>
      </tr>
      <!-- 繰り返し終わり -->
    </tbody>
  </table>

  <!-- 確認 n/N の n は部品6 JS が復元・操作のたびに上書きする。N の初期値だけここに書く -->
  <p class="approval-progress">確認 <span id="approvedCount">0</span>/<span id="approvalTotal">{approvalTotal}</span></p>
</header>

<!-- ═══ 部品2: 受け入れ基準節 ═══ -->
<!-- spec (無ければ plan) に受け入れ基準が無ければこの節ごと省略する。チェックさせない — 挙動ゲート通過済みの記録として並べるだけ -->
<!-- spec のテストケース表は 1 行 1 項目に畳む: 「<seam> — <ケース> → <期待結果>」。「テストしないと決めたもの」は通過記録ではないので載せない -->
<section class="acceptance-section">
  <h2 class="section-head">受け入れ基準</h2>
  <ul class="acceptance-list">
    <!-- 繰り返し: 基準 -->
    <li class="acceptance-item"><span class="acceptance-mark">✓</span>{criterionText}</li>
    <!-- 繰り返し終わり -->
  </ul>
</section>

<!-- ═══ 部品3: セクション見出し ═══ -->
<h2 class="section-head section-head--escalated">01 昇格 (人間が見る)</h2>
<!-- ここに昇格した details.file (部品5A・部品7 の決裁カード・部品5B をこの順で含む) を並べる。open がデフォルト -->

<h2 class="section-head section-head--folded">02 非昇格 (畳み済み)</h2>
<!-- 繰り返し: グループ (そのグループに非昇格 hunk が1件も残らないなら、このグループ丸ごと省略してよい) -->
<div class="group-block">
  <h3 class="group-head">{groupName} <span class="group-tag">{tag}</span></h3>
  <p class="group-intent">{intentText}</p>
  <!-- このグループに属する非昇格 hunk だけを収めた details.file (既定 closed) をこの直下に並べる -->
</div>
<!-- 繰り返し終わり -->

<!-- ═══ 部品4: 昇格理由バッジ ═══ -->
<!-- 置き場所は部品7 決裁カードの見出し行 (.decision-head) の先頭。1 hunk に複数バッジ可 -->
<!-- hunk-head 側には入れない — 昇格 hunk の diff は既定で畳まれており、開かないと昇格理由が見えなくなるため -->
<!-- 番号↔短ラベルの対応は固定 (自分で言い換えない): ①不可逆 ②対外境界 ③依存追加 ④指摘あり ⑤逸脱 ⑥未分類 -->
<!-- ①②は escalation-badge--critical、③〜⑥は escalation-badge--notice -->
<!-- 繰り返し: バッジ (該当した昇格理由の数だけ。例は①③の2個同時該当) -->
<span class="escalation-badge escalation-badge--critical">① 不可逆</span>
<span class="escalation-badge escalation-badge--notice">③ 依存追加</span>
<!-- 繰り返し終わり -->

<!-- ═══ 部品5: 承認チェック ═══ -->

<!-- 5A: 状態バッジ — 昇格ファイルの file-head 内、.file-name の直後に挿入する (file-head 自体は templates.md 正本のまま。挿入点を示す最小文脈のみ) -->
<summary class="file-head">
  <span class="file-badge mod">変更</span>
  <span class="file-name">{path}</span>
  <span class="approval-state">未確認</span>
  <!-- 以下 mark.sev-* / .file-meta は templates.md 正本のまま続く -->
</summary>

<!-- 5B: 承認チェック本体 — 昇格ファイルの details.file の末尾 (最後の決裁カードの直後) に置く -->
<!-- 対象の details.file には data-escalated="true" を必ず付ける (部品6 JS が昇格ファイルの判定に使う固定 data 属性) -->
<!-- ラベルは決裁の文言に固定する。「diff を読んだ」に戻さない — 求めているのはリスクの受容であって読了報告ではない -->
<div class="approval-check">
  <label class="approval-check-label">
    <input type="checkbox" class="approval-checkbox">
    このリスクを受け入れる
  </label>
</div>

<!-- ═══ 部品7: 決裁カード ═══ -->
<!-- 昇格 hunk 1 件につき 1 枚。昇格ファイルの details.file の中に、その hunk の数だけ並べる -->
<!-- 組み立て順 (昇格ファイル1つ分):
     <details class="file" data-escalated="true" open>
       <summary class="file-head">…部品5A…</summary>
       <div class="decision-card">…</div>   ← 昇格 hunk の数だけ繰り返す
       <div class="approval-check">…部品5B…</div>
     </details> -->
<!-- dt の 4 語は固定。順序も入れ替えない (何が起きうるか → 元に戻せるか → 影響範囲 → AI レビュー) -->
<!-- 書いてよいのは素材 (diff・plan・spec・Step2 の指摘欄) にある事実だけ。読み取れないことは文頭に「推測:」を付ける -->
<!-- 繰り返し: 決裁カード (そのファイルの昇格 hunk の数だけ) -->
<div class="decision-card">
  <div class="decision-head">
    <!-- 繰り返し: 昇格理由バッジ (部品4。該当した昇格理由の数だけ) -->
    <span class="escalation-badge escalation-badge--critical">① 不可逆</span>
    <!-- 繰り返し終わり -->
    <span class="decision-locus">{hunkLocus}</span>
    <span class="decision-group">{groupName}</span>
  </div>
  <dl class="decision-points">
    <dt>何が起きうるか</dt>
    <dd>{whatCanHappen}</dd>
    <dt>元に戻せるか</dt>
    <!-- 可逆 = risk-badge risk-low「可逆」/ 不可逆 = risk-badge risk-warn「不可逆」の2択。第3の値を作らない -->
    <dd><span class="risk-badge risk-warn">不可逆</span>{reversibilityNote}</dd>
    <dt>影響範囲</dt>
    <dd>{blastRadius}</dd>
    <dt>AI レビューの判定</dt>
    <!-- 出所は Step2 の指摘欄と plan の ## Deviations だけ。どちらにも無ければ「指摘なし」と書く (判定を創作しない) -->
    <dd>{reviewVerdict}</dd>
  </dl>
  <details class="decision-diff">
    <summary class="decision-diff-head">diff を見る ({hunkStat})</summary>
    <!-- ここに templates.md 正本の .hunk ブロック (hunk-head + diff-body > diff-table) を1つ、無改変で置く -->
  </details>
</div>
<!-- 繰り返し終わり -->

<!-- ═══ 固有部品CSS (部品1〜5・7共通・無改変層) ═══ -->
<style>
/* 部品1: ヘッダブロック */
.review-header { margin: 0 0 28px; }
.review-title { margin: 0 0 .3em; font-size: 1.8em; font-weight: 700; letter-spacing: -0.02em; color: var(--ink); font-family: var(--sans); }
.review-stats { margin: 0 0 .4em; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-family: var(--mono); font-size: 0.92em; color: var(--muted); }
.review-summary { margin: 0 0 14px; font-size: 1.02em; color: var(--body); }
.review-summary strong { color: var(--ink); }
.group-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.88em; }
.group-table th, .group-table td { border: 1px solid var(--hairline); padding: 6px 10px; text-align: left; vertical-align: top; }
.group-table th { background: var(--th-bg); color: var(--th-fg); font-size: 0.82em; font-weight: 600; letter-spacing: 0.03em; }
.group-table tr:nth-child(2n) td { background: var(--canvas-soft); }
.group-tag { display: inline-block; padding: 1px 7px; border-radius: 4px; background: var(--surface-strong); color: var(--muted); font-family: var(--mono); font-size: 0.85em; }
.group-escalated { margin-left: 6px; color: var(--muted); font-size: 0.9em; }
.approval-progress { margin: 14px 0 0; padding: 8px 12px; display: inline-block; border-radius: var(--radius-md); background: var(--canvas-soft); border: 1px solid var(--hairline); font-family: var(--mono); font-size: 0.9em; color: var(--ink); }

/* リスクバッジ (部品1 グループ集計表内で使用) */
.risk-badge { display: inline-block; padding: 1px 8px; border-radius: 9999px; font-size: 0.78em; font-weight: 600; }
.risk-badge.risk-low { background: var(--surface-strong); color: var(--muted); }
.risk-badge.risk-caution { background: var(--primary-tint); color: var(--primary); }
.risk-badge.risk-warn { background: var(--diff-del-bg); color: var(--diff-del-fg); }
html[data-theme="dark"] .risk-badge.risk-warn { color: var(--diff-del-fg-onwash); }

/* 部品2: 受け入れ基準節 */
.acceptance-section { margin: 0 0 28px; }
.acceptance-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.acceptance-item { display: flex; align-items: flex-start; gap: 8px; color: var(--body); }
.acceptance-mark { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; margin-top: 2px; border-radius: 9999px; background: var(--diff-add-bg); color: var(--diff-add-fg); font-size: 0.75em; font-weight: 700; }

/* 部品3: セクション見出し */
.section-head { margin: 2em 0 0.8em; padding: 0 0 0.3em 12px; border-bottom: 1px solid var(--hairline); border-left: 4px solid var(--hairline-strong); font-size: 1.3em; font-weight: 700; letter-spacing: -0.015em; color: var(--ink); }
.section-head--escalated { border-left-color: var(--diff-del-fg); }
.section-head--folded { border-left-color: var(--muted); }
.group-block { margin: 1.4em 0 0.6em; }
.group-head { margin: 0 0 0.3em; display: flex; align-items: center; gap: 8px; font-size: 1.05em; font-weight: 600; color: var(--ink); }
.group-intent { margin: 0 0 0.8em; color: var(--body); font-size: 0.95em; }

/* 部品4: 昇格理由バッジ */
.escalation-badge { display: inline-block; margin-right: 6px; padding: 1px 8px; border-radius: 9999px; font-family: var(--sans); font-size: 0.78em; font-weight: 600; letter-spacing: 0.02em; }
.escalation-badge--critical { background: var(--diff-del-bg); color: var(--diff-del-fg); }
.escalation-badge--notice { background: var(--primary-tint); color: var(--primary); }
html[data-theme="dark"] .escalation-badge--critical { color: var(--diff-del-fg-onwash); }

/* 部品5: 承認チェック */
.approval-state { flex: 0 0 auto; padding: 2px 8px; border-radius: 9999px; background: var(--surface-strong); color: var(--muted); font-family: var(--sans); font-size: 0.72em; font-weight: 600; }
.approval-state.approval-state--done { background: var(--diff-add-bg); color: var(--diff-add-fg); }
.approval-check { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--hairline); }
.approval-check-label { display: flex; align-items: center; gap: 8px; color: var(--body); font-family: var(--sans); font-size: 0.92em; cursor: pointer; }
.approval-checkbox { width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer; }
/* details.file が承認済みのときの視覚補強 (部品6 JS が .approved を付け外しする) */
.file.approved > .file-head { background: var(--diff-add-bg); }
/* ファイルナビ項目への状態反映 (部品6 JS が対応する <a> に nav-approved を付け外しする) */
.file-nav-item a.nav-approved { color: var(--diff-add-fg); }
.file-nav-item a.nav-approved::after { content: "✓"; margin-left: 6px; font-weight: 700; }

/* 部品7: 決裁カード */
.decision-card { padding: 12px 14px; }
/* 区切り線はカード同士の間だけ。末尾に線を残すと承認チェックの破線と二重になる */
.decision-card + .decision-card { border-top: 1px solid var(--hairline); }
.decision-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 8px; }
.decision-locus { font-family: var(--mono); font-size: 0.8em; color: var(--muted); }
.decision-group { font-family: var(--sans); font-size: 0.8em; color: var(--muted); }
.decision-points { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 5px 14px; font-size: 0.93em; }
.decision-points dt { color: var(--muted); font-family: var(--sans); font-weight: 600; white-space: nowrap; }
.decision-points dd { margin: 0; color: var(--body); }
.decision-points dd .risk-badge { margin-right: 6px; }
.decision-diff { margin-top: 10px; border: 1px solid var(--hairline); border-radius: var(--radius-md); overflow: hidden; background: var(--surface-card); }
.decision-diff-head { padding: 6px 12px; background: var(--canvas-soft); cursor: pointer; list-style: none; font-family: var(--sans); font-size: 0.85em; color: var(--muted); }
.decision-diff-head::-webkit-details-marker { display: none; }
.decision-diff-head::before { content: "▸"; display: inline-block; margin-right: 6px; transition: transform 0.12s ease; }
.decision-diff[open] > .decision-diff-head::before { transform: rotate(90deg); }
/* 開いた直後の hunk-head は decision-diff-head のすぐ下に来る。上線を残すと境界が二重になる */
.decision-diff .hunk:first-of-type .hunk-head { border-top: 0; }
@media (max-width: 700px) {
  .decision-points { grid-template-columns: 1fr; gap: 2px; }
  .decision-points dd { margin: 0 0 6px; }
}
</style>

<!-- ═══ 部品6: 承認JS (無改変層・templates.md のファイルナビ生成スクリプトより後に置く) ═══ -->
<script>
(function () {
  var STORAGE_KEY = 'diff-review:' + location.pathname.split('/').pop();
  // 昇格ファイル (details.file[data-escalated="true"]) の中のチェックだけを扱う。
  // ここで絞ってあるので、以降 closest は必ず要素を返す。
  var checkboxes = Array.prototype.slice.call(document.querySelectorAll('.approval-checkbox'))
    .filter(function (cb) { return !!cb.closest('details.file[data-escalated="true"]'); });
  if (!checkboxes.length) return;

  var countEl = document.getElementById('approvedCount');
  var totalEl = document.getElementById('approvalTotal');
  var navList = document.getElementById('fileNavList');

  // 保存キーは位置ではなく内容 (ファイル名 + そのファイル先頭の決裁カードの位置) から作る。
  // details.file の id は登場順の連番 (file-1, file-2 …) なので、id をキーにすると
  // 同じ日に同じ slug で作り直したレポートに別ファイルの承認が復元される。
  function keyFor(cb) {
    var file = cb.closest('details.file[data-escalated="true"]');
    var name = file.querySelector('.file-name');
    var locus = file.querySelector('.decision-locus');
    return (name ? name.textContent.trim() : (file.id || '')) + (locus ? '|' + locus.textContent.trim() : '');
  }

  function applyState(cb, approved) {
    cb.checked = approved;
    var file = cb.closest('details.file[data-escalated="true"]');
    file.classList.toggle('approved', approved);
    var badge = file.querySelector('.approval-state');
    if (badge) {
      badge.classList.toggle('approval-state--done', approved);
      badge.textContent = approved ? '✓ 確認済み' : '未確認';
    }
    if (navList) {
      var link = navList.querySelector('a[href="#' + file.id + '"]');
      if (link) link.classList.toggle('nav-approved', approved);
    }
  }

  function updateProgress() {
    var done = checkboxes.filter(function (cb) { return cb.checked; }).length;
    if (countEl) countEl.textContent = String(done);
    if (totalEl) totalEl.textContent = String(checkboxes.length);
  }

  function save() {
    var state = {};
    checkboxes.forEach(function (cb) { state[keyFor(cb)] = cb.checked; });
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
  }

  function restore() {
    var raw = null;
    try { raw = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (!raw) return;
    var state;
    try { state = JSON.parse(raw); } catch (e) { return; }
    checkboxes.forEach(function (cb) {
      if (state[keyFor(cb)]) applyState(cb, true);
    });
  }

  checkboxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      applyState(cb, cb.checked);
      updateProgress();
      save();
    });
  });

  restore();
  updateProgress();
})();
</script>
```
<!-- TEMPLATE:END -->
