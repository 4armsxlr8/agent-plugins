# diff-review 固有コンポーネント — 正本仕様

diff-review のレポートで使う **diff-review 固有部品の唯一の正本**。ページ骨格・タブ・diff テーブル・ファイルナビは派生元 `../../html-report/references/templates.md` と `../../html-report/assets/style.css` が正本であり、本ファイルは**その上に足す部品だけ**を定義する (基盤側の構造を再掲しない — 同じ要素の正本が2つあると必ず乖離する)。

## なぜ正本を固定するか

バッジ・ヘッダ集計・承認チェック・保存 JS は従来 SKILL.md の散文指示だけで定義されており、生成のたびに fork がマークアップ・CSS・JS を即興で発明していた。散文は「何を作るか」は固定できても「どう見えるか」は固定できない。完全に書き下した部品 (templates.md のファイルナビ JS) が揺れなかった実績に合わせ、固有部品も全部品を書き下す。

## 契約 — 2層 (どこまで無改変か)

| 層 | 対象 | 扱い |
|---|---|---|
| **無改変層** | 本ファイルの `<style>` ブロックと `<script>` ブロック | 一字も変えずにレポートへ貼る |
| **スロット層** | 本ファイルのマークアップ雛形 | 骨格は無改変。`{…}` プレースホルダの中身と、`<!-- 繰り返し: … -->` コメント直下の行の反復回数**だけ**を差し替える。要素・class の追加削除・並べ替えはしない |

- プレースホルダ規約: `{title}` のような `{}` 単一値と、`<!-- 繰り返し: <単位> -->` の直下1ブロックを反復する2形式のみ
- 色は必ず style.css の CSS 変数経由。**新しい色・新しい class を発明しない**。部品が足りないと感じたら即興で足さず、本ファイルへの追記として提案する (正本の外に生まれた部品は次の生成で消える)

## 部品一覧 (この6つで全固有部品)

1. **ヘッダブロック** — タイトル、`N files / M hunks +a -d` 統計、要約行「人間が見るべき箇所 N 件 / 全 M hunk」、グループ集計表 (グループ名・タグ・リスク・hunk 数「うち昇格 n」・指摘)、承認プログレス「確認 0/N」
2. **受け入れ基準節** — 挙動ゲート通過済みの記録としての表示専用リスト (チェックさせない)
3. **セクション見出し** — `01 昇格 (人間が見る)` / `02 非昇格 (畳み済み)` の2見出しと、02 のグループ単位の小見出し + 意図解説
4. **昇格理由バッジ** — `hunk-head` 内に置く ①〜⑥ のバッジ (複数可)。**形は全種共通・色は2系統のみ**: ①② (不可逆・対外境界) = `--diff-del-bg` 地 + `--diff-del-fg` 字、③〜⑥ = `--primary-tint` 地 + `--primary` 字。番号 + 短ラベル (例: `① 不可逆`) で種別を運ぶ — 6色に塗り分けない (トークンに6色は無く、発明した色は揺れの再発源になる)
5. **承認チェック** — 昇格ファイルの `<details class="file">` **内の末尾**に置くチェックブロック (ラベルは「挙動確認済み + この昇格箇所を見た」の宣言)。`file-head` への状態バッジ (✓ 確認済み / 未確認) は **`.file-name` の直後に挿入**する (file-head 自体の構造は templates.md の正本のまま)。**昇格 0 件のときの宣言チェック1個の variant** もここで定義する
6. **承認 JS** — チェック変更で `details.file` に `.approved` を付け外しし、状態バッジ・ファイルナビ・ヘッダの「確認 n/N」カウンタへ反映、localStorage へ保存する。**templates.md のファイルナビ生成スクリプトより後に置く** (ナビ項目を装飾するため)。キーは `diff-review:` + レポートのファイル名 (`location.pathname` の basename)。**復元時はカウンタだけでなく `.approved`・状態バッジ・ナビ表示も再適用する**

## class 命名

style.css の既存イディオムに合わせる (セマンティックな kebab-case、接頭辞なし — この部品はスキル自身のページ内で完結するため、tweak-panel のような防御接頭辞は不要)。**style.css / templates.md で定義済みの class 名と衝突しないこと** (追加前に grep で確認する)。

## テンプレート

<!-- TEMPLATE:BEGIN -->
```html
<!--
  diff-review 固有部品 — components.md の「テンプレート」節へそのまま埋め込む断片。
  無改変層: <style> と <script> は一字も変えずに貼る。
  スロット層: マークアップ雛形は {…} と <!-- 繰り返し: … --> の中身・反復回数だけ差し替える。
  部品1〜5は report-main (templates.md の .report-layout > .report-main) の中に置く。
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
<!-- plan に受け入れ基準が無ければこの節ごと省略する。チェックさせない — 挙動ゲート通過済みの記録として並べるだけ -->
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
<!-- ここに昇格した details.file (部品4・部品5A/5Bを含む) を並べる。open がデフォルト -->

<h2 class="section-head section-head--folded">02 非昇格 (畳み済み)</h2>
<!-- 繰り返し: グループ (そのグループに非昇格 hunk が1件も残らないなら、このグループ丸ごと省略してよい) -->
<div class="group-block">
  <h3 class="group-head">{groupName} <span class="group-tag">{tag}</span></h3>
  <p class="group-intent">{intentText}</p>
  <!-- このグループに属する非昇格 hunk だけを収めた details.file (既定 closed) をこの直下に並べる -->
</div>
<!-- 繰り返し終わり -->

<!-- ═══ 部品4: 昇格理由バッジ ═══ -->
<!-- 昇格した hunk の hunk-head 内、テキストの直前に差し込む (hunk-head 自体は templates.md 正本のまま)。1 hunk に複数バッジ可 -->
<!-- 番号↔短ラベルの対応は固定 (自分で言い換えない): ①不可逆 ②対外境界 ③依存追加 ④指摘あり ⑤逸脱 ⑥未分類 -->
<!-- ①②は escalation-badge--critical、③〜⑥は escalation-badge--notice -->
<div class="hunk-head">
  <!-- 繰り返し: バッジ (該当した昇格理由の数だけ。例は①③の2個同時該当) -->
  <span class="escalation-badge escalation-badge--critical">① 不可逆</span>
  <span class="escalation-badge escalation-badge--notice">③ 依存追加</span>
  <!-- 繰り返し終わり -->
  hunk 1/5 — @@ 3,7 → 3,7 @@ セッション検証の前後
</div>

<!-- ═══ 部品5: 承認チェック ═══ -->

<!-- 5A: 状態バッジ — 昇格ファイルの file-head 内、.file-name の直後に挿入する (file-head 自体は templates.md 正本のまま。挿入点を示す最小文脈のみ) -->
<summary class="file-head">
  <span class="file-badge mod">変更</span>
  <span class="file-name">{path}</span>
  <span class="approval-state">未確認</span>
  <!-- 以下 mark.sev-* / .file-meta は templates.md 正本のまま続く -->
</summary>

<!-- 5B: 承認チェック本体 — 昇格ファイルの details.file の末尾 (最後の hunk・note の直後) に置く -->
<!-- 対象の details.file には data-escalated="true" を必ず付ける (部品6 JS が昇格ファイルの判定に使う固定 data 属性) -->
<!-- 例: <details class="file" data-escalated="true" open> … <div class="approval-check">(このブロック)</div></details> -->
<div class="approval-check">
  <label class="approval-check-label">
    <input type="checkbox" class="approval-checkbox">
    挙動確認済み・この昇格箇所を見た
  </label>
</div>

<!-- 5C: 昇格0件のときの variant — 5B の代わりにページに1個だけ置く (details.file には紐付かない) -->
<div class="approval-check approval-check--standalone" id="approval-global">
  <label class="approval-check-label">
    <input type="checkbox" class="approval-checkbox">
    <span class="approval-check-text">挙動確認済み・昇格該当なし</span>
  </label>
</div>

<!-- ═══ 固有部品CSS (部品1〜5共通・無改変層) ═══ -->
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
html[data-theme="dark"] .risk-badge.risk-warn { color: #ff8781; }

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
html[data-theme="dark"] .escalation-badge--critical { color: #ff8781; }

/* 部品5: 承認チェック */
.approval-state { flex: 0 0 auto; padding: 2px 8px; border-radius: 9999px; background: var(--surface-strong); color: var(--muted); font-family: var(--sans); font-size: 0.72em; font-weight: 600; }
.approval-state.approval-state--done { background: var(--diff-add-bg); color: var(--diff-add-fg); }
.approval-check { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--hairline); }
.approval-check-label { display: flex; align-items: center; gap: 8px; color: var(--body); font-family: var(--sans); font-size: 0.92em; cursor: pointer; }
.approval-checkbox { width: 16px; height: 16px; accent-color: var(--primary); cursor: pointer; }
.approval-check--standalone.is-approved .approval-check-text { color: var(--diff-add-fg); font-weight: 600; }
/* details.file が承認済みのときの視覚補強 (部品6 JS が .approved を付け外しする) */
.file.approved > .file-head { background: var(--diff-add-bg); }
/* ファイルナビ項目への状態反映 (部品6 JS が対応する <a> に nav-approved を付け外しする) */
.file-nav-item a.nav-approved { color: var(--diff-add-fg); }
.file-nav-item a.nav-approved::after { content: "✓"; margin-left: 6px; font-weight: 700; }
</style>

<!-- ═══ 部品6: 承認JS (無改変層・templates.md のファイルナビ生成スクリプトより後に置く) ═══ -->
<script>
(function () {
  var STORAGE_KEY = 'diff-review:' + location.pathname.split('/').pop();
  var checkboxes = Array.prototype.slice.call(document.querySelectorAll('.approval-checkbox'));
  if (!checkboxes.length) return;

  var countEl = document.getElementById('approvedCount');
  var totalEl = document.getElementById('approvalTotal');
  var navList = document.getElementById('fileNavList');

  // 昇格ファイルの判定は data-escalated="true" (details.file 側に付ける固定属性) から行う。
  // チェックボックス自身は details.file の子孫かどうかで file 紐付き/5C(単独)を判定する。
  function keyFor(cb) {
    var file = cb.closest('details.file[data-escalated="true"]');
    if (file) return file.id;
    var standalone = cb.closest('.approval-check');
    return (standalone && standalone.id) || '__all-clear__';
  }

  function applyState(cb, approved) {
    cb.checked = approved;
    var file = cb.closest('details.file[data-escalated="true"]');
    if (file) {
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
    } else {
      var standalone = cb.closest('.approval-check');
      if (standalone) standalone.classList.toggle('is-approved', approved);
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
