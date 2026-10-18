# html-report — マークアップ雛形

ページの骨格と、diff 表示まわりの部品の正本。**部品の見た目 (CSS) の正本は `../assets/style.css`、実物は `../assets/component-samples.html`、図は `diagrams.md`** — このファイルはマークアップの並びだけを持つ。

## 共通骨格

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
/* 同梱の assets/style.css の中身を丸ごとここに貼る (部品CSSも含まれている) */
</style>
<script>
/* 同梱の assets/htmlplan.js の中身を丸ごとここに貼る (doc-* 部品・コメント・Respond・左レール目次の runtime) */
</script>
</head>
<body data-numbers="off">   <!-- 見出しの番号は style.css の counter (01, 02 …) が振る。runtime の §1 は切る -->
<button class="theme-toggle" id="themeToggle" type="button" aria-label="テーマ切り替え">◐</button>
<!-- <main> はどちらか一方を使う:
     散文レポート用 (html-report)      <main class="report markdown-body report-numbered">
     diff レポート用 (diff-review)     <main class="report report-numbered">
     diff 側で markdown-body を外すのは、`.markdown-body table` のような子孫セレクタ
     (詳細度 0,1,1) が diff-review 固有部品の単一 class (0,1,0) に勝ってしまうため。 -->
<main class="report markdown-body report-numbered">
<header class="report-head">
  <h1>{title}</h1>
  <p class="report-meta"><span class="badge plain">{type}</span><span>{YYYY-MM-DD}</span><span>素材: {素材の短い説明}</span></p>
  <p class="lede">{レポートの概要 1 文}</p>
</header>

<div class="keypoints">…</div>

<!-- 目次は書かない。runtime が h2 / h3 / doc-ask から左レールに組む (1180px 以上。狭い画面は右下の ☰) -->

<!-- 節は details.sec の行。h2 は必ず summary の中 (閉じた details の中身は描画されず、採番から漏れるため)。
     中身は <section> にする — runtime は section > p と li にコメントボタンを付ける (div だと付かない) -->
<details class="sec" open>
  <summary class="sec-head"><h2 id="s-1">…</h2><span class="sec-meta">…</span></summary>
  <section class="sec-body">…</section>
</details>
<!-- 詳細・根拠の節は open を付けずに閉じて出す -->
</main>
<script>
(function () {
  /* テーマ: style.css は html[data-theme="dark"] だけを見るので、初期値を JS で入れる */
  var root = document.documentElement;
  var KEY = 'crystallize-report-theme';
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
  var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = (saved === 'dark' || saved === 'light') ? saved : (prefersDark ? 'dark' : 'light');

  var btn = document.getElementById('themeToggle');
  if (btn) {
    btn.addEventListener('click', function () {
      var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch (e) { /* プライベートウィンドウ等 */ }
    });
  }
})();
</script>
<script>
(function () {
  /* 閉じた節の中へ飛ぶとき (左レール目次・ハッシュ) は節を開いてから。印刷前は全節を開く */
  function openFor(el) {
    var d = el && el.closest('details');
    while (d) { d.open = true; d = d.parentElement && d.parentElement.closest('details'); }
  }
  /* 飛び先が貼り付く行の中の見出しだと、ブラウザは貼り付きの終点 (節の末尾) に合わせてしまい中身が映らない。
     見出しではなく節の器 (details) の上端へ飛ぶ */
  function jumpTo(el) {
    if (!el) return;
    openFor(el);
    var box = el.closest('summary') ? el.closest('details') : el;
    box.scrollIntoView({ block: 'start' });
  }
  function byHash(h) { return h ? document.getElementById(decodeURIComponent(h.slice(1))) : null; }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="#"]');
    var t = a && byHash(a.getAttribute('href'));
    if (!t) return;
    e.preventDefault();
    jumpTo(t);
    if (history.replaceState) history.replaceState(null, '', a.getAttribute('href'));
  }, true);   /* capture: runtime のクリック処理 (シートを閉じる) はそのまま走る */
  function openHash() { var t = byHash(location.hash); jumpTo(t); setTimeout(function () { jumpTo(t); }, 120); }   /* runtime が 60ms 後に見出しへ再スクロールするので、その後でもう一度 */
  window.addEventListener('hashchange', openHash);
  openHash();
  window.addEventListener('beforeprint', function () {
    Array.prototype.forEach.call(document.querySelectorAll('details.sec'), function (d) { d.open = true; });
  });
})();
</script>
</body>
</html>
```

- 題の直下は `header.report-head`: `h1` → `p.report-meta` (種別 `badge plain` と日付。素材の説明は任意) → `p.lede`(概要 1 文)。report-index は `p.lede` を一覧の説明文に拾うので、class 名を変えない
- **本文の節は `details.sec` の行にする** (下の「節の行」)。目次は書かない — `<head>` に貼った runtime が h2 / h3 / doc-ask から左レール (1180px 以上) と ☰ のシート (狭い画面) を組む。本文の番号 (01, 02 …) は style.css の counter が h2 とレールの両方に振るので、`<body data-numbers="off">` を外さない (外すと runtime が §1 を重ねて振る)
- **`assets/htmlplan.js` は `<head>` の `<script>` に無改変で貼る**。コード (`doc-code`)・呼び出し木 (`doc-calls`)・図 (`doc-flow` ほか)・コメントと Respond・左レール目次はすべてこれが描く。文法は `blocks.md`
- 上の 2 つ目の `<script>`(閉じた節を開いてから飛ぶ・印刷前の展開)は **無改変で入れる**。無いと、閉じた節への目次リンクが何も表示しないまま終わり、印刷で閉じた節が紙から消える
- `<main>` の class は **散文レポート (html-report) なら 3つセット**: `report`(幅とパディング) + `markdown-body`(本文タイポグラフィ) + `report-numbered`(h2 の自動採番)
- **diff レポート (diff-review) は `markdown-body` を付けず `report report-numbered` の2つにする** — `markdown-body` の子孫セレクタが `references/components.md` の固有部品 (単一 class) に詳細度で勝ち、無改変層で貼ったはずの見た目が崩れる
- **テーマ切替ボタンと上の初期化 JS は無改変で入れる** — style.css のダーク配色は `html[data-theme="dark"]` でしか適用されない。この JS が無いと、OS がダークでもライトのまま出る
- **本レポート用の追記 CSS を書かない**。部品は style.css に揃っている。足りない部品は style.css への追記として提案する(その場で書いた CSS は次の生成で消え、レポートごとの見た目の揺れになる)

## タブ(依存ライブラリなし)

```html
<nav class="tabs">
  <button class="tab active" data-pane="p1" type="button">概要</button>
  <button class="tab" data-pane="p2" type="button">詳細</button>
</nav>
<section id="p1" class="pane active">…</section>
<section id="p2" class="pane">…</section>
<script>
document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.tab,.pane').forEach(e => e.classList.remove('active'));
  b.classList.add('active');
  document.getElementById(b.dataset.pane).classList.add('active');
}));
</script>
```

- `.tabs` / `.tab` / `.pane` の CSS は style.css にある。印刷時は全ペインが開いてタブ列が消える(畳んだ内容を紙から落とさないため)
- **`h2` は `.pane` の外に置く(タブの中は `h3` 以下)** — 非表示のペイン内の `h2` は採番されず、本文と目次の番号がずれる

## 要点(全レポート共通・先頭固定)

```html
<div class="keypoints">
  <ol><li>…最大3点、1点1文…</li></ol>
</div>
```

- **見出しを書かない**。「要点」のラベルは `.keypoints::before` が付ける — 文言と位置をレポート側に任せると「結論」「サマリ」と揺れる
- 目次は書かない。runtime が h2 / h3 / doc-ask から左レールに組み、番号は CSS counter が振る(`.report-toc` の CSS は古いレポートのために残してあるだけで、新しいレポートでは使わない)

## 節の行(h2 の節はすべてこの形)

```html
<details class="sec" open>
  <summary class="sec-head">
    <h2 id="s-candidates">取り込み候補</h2>
    <span class="sec-meta">11 件</span>
  </summary>
  <section class="sec-body">
    <p>…</p>
    <!-- 小節 (h3) も同じ形で入れ子にできる。入れ子は線が薄く、行が低くなる -->
    <details class="sec" open>
      <summary class="sec-head"><h3>やり取りを減らす</h3><span class="sec-meta">5 件</span></summary>
      <section class="sec-body">…</section>
    </details>
  </section>
</details>
```

- 1 行 = 番号 + 見出し + 右端の `sec-meta`(中身の量を 2〜4 文字で: `3 案` `図 2` `11 件` `全文`)。`sec-meta` が書けないときは省く(空の span を置かない)
- `sec-body` は `<section>` にする(`<div>` にしない)— runtime は `section > p` と `li` にコメントボタンを付けるので、div だと段落にコメントできない
- **h2 は `summary.sec-head` の中に置く。`sec-body` の中に h2 を書かない** — 閉じた details の中身は描画されないため、そこにある h2 は採番されず、本文と目次の番号がずれる
- 用語と本論の節は `open`。**詳細・根拠の節は `open` を付けず閉じて出す** — 畳んで短く見せる、の実体がこの行。閉じた節への目次リンクは骨格の JS が開いてから飛ぶ
- 開いている節の行は画面上部に貼り付く(長い節の途中でも今どの節かが分かる)。入れ子の行は貼り付かない
- タブ(`.tabs`/`.pane`)は `sec-body` の中に置く。h2 を `.pane` の中に入れない規則はそのまま

## 比較グリッド + トレードオフ表(compare)

```html
<div class="cards">
  <section class="card">
    <h3>案A <span class="badge">推奨</span></h3>
    <p>一言サマリ</p>
    <dl><dt>強み</dt><dd>…</dd><dt>弱み</dt><dd>…</dd></dl>
  </section>
  <!-- 案B, 案C … 推奨以外のバッジは class="badge plain" -->
</div>
```

- トレードオフ表は「行=評価軸、列=案」。セルは ◎○△ + 一言(記号だけにしない — 理由が読めないと判断材料にならない)
- 推奨は1案にバッジを付け、根拠を表の直下に1〜2文で書く

## ラウンド (round) — spec のラウンドレポート

`spec` スキルの画面のあるタスクで、1 ラウンドの問いを置くレポート。絵 (案) はデザインキャンバス (Design 型 Artifact) にアートボードとして描かれていて、レポートに載せるのはそのスクリーンショットとリンクだけ。**案をレポートの HTML で描き直さない** (絵の正本が 2 つになる)。出力先は `out:` (`docs/crystallize/specs/<slug>/round-<n>.html` の絶対パス。呼び出し元がリポジトリルートで解決する)、`open` と report-index 登録はしない。絵の無いラウンド (第 1 ラウンドなど) も同じ種別で作る。

### 素材の形 (呼び出し元の spec が書く)

```yaml
slug: share-card-link
round: 3
canvas: https://claude.ai/artifact/…        # デザインキャンバスの URL。artboards のある問いが 1 つでもあれば必須、無ければ省く
reader: 対象読者と、説明なしで使ってよい語の 1 行
questions:
  - id: q1
    title: 一覧の形
    question: 作品の一覧をどう見せるか
    premise: 投稿者が、公開直後に自分の作品を見つけて共有リンクを取る場面。R2 で検索欄は不採用
    recommended: a
    reason: 件数が 20 件を超えても 1 画面で見渡せる
    options:
      - id: a
        label: カードグリッド
        gain: 画像で作品を見分けられる
        loss: 題名の全文は一覧では読めない
        artboards:
          - name: R3-Q1-A
            png: /abs/path/docs/crystallize/specs/share-card-link/design/round-3/project/R3-Q1-A.png   # 絶対パス
      - id: b
        label: 縦リスト (提案)
        gain: 題名と日付で探せる
        loss: 画像では見分けられない
        artboards:
          - name: R3-Q1-B
            png: null                         # ローカルで描けない案。リンクだけ
            note: デザインシステムの部品を使うため、キャンバスで確認
  - id: q2
    title: カードの間隔
    kind: range                               # 値の問い。min / max / step / value (推奨値) / unit
    question: カードの間隔をいくつにするか
    premise: …
    min: 8
    max: 24
    step: 4
    value: 12
    unit: px
```

`artboards` の無い問いは文だけの問い (第 1 ラウンドなど)。`kind: range` の無い問いは radio。`png` と `out:` は絶対パス (fork の cwd は保証されない)。

### マークアップ

```html
<details class="sec" open>
  <summary class="sec-head"><h2 id="s-questions">問い</h2><span class="sec-meta">3 問</span></summary>
  <section class="sec-body">

    <details class="sec" open>
      <summary class="sec-head"><h3 id="q1">Q1 一覧の形</h3><span class="sec-meta">2 案</span></summary>
      <section class="sec-body">
        <p><strong>前提:</strong> 投稿者が、公開直後に自分の作品を見つけて共有リンクを取る場面。R2 で検索欄は不採用</p>
        <doc-ask id="q1">
          <p>作品の一覧をどう見せるか</p>
          <label><input type="radio" name="q1" value="a" checked> A カードグリッド <small>推奨。件数が 20 件を超えても 1 画面で見渡せる</small></label>
          <label><input type="radio" name="q1" value="b"> B 縦リスト (提案)</label>
        </doc-ask>
        <div class="cards">
          <section class="card">
            <h4>A カードグリッド <span class="badge">推奨</span></h4>
            <figure class="figure">
              <img src="data:image/png;base64,…" alt="R3-Q1-A">
              <figcaption>R3-Q1-A — <a href="https://claude.ai/artifact/…">キャンバスで開く</a></figcaption>
            </figure>
            <dl><dt>できるようになる</dt><dd>画像で作品を見分けられる</dd><dt>できなくなる</dt><dd>題名の全文は一覧では読めない</dd></dl>
          </section>
          <section class="card">
            <h4>B 縦リスト (提案) <span class="badge plain">提案</span></h4>
            <p class="note">R3-Q1-B — <a href="https://claude.ai/artifact/…">キャンバスで開く</a>。デザインシステムの部品を使うためローカルでは描けず、スクリーンショットは無い</p>
            <dl><dt>できるようになる</dt><dd>題名と日付で探せる</dd><dt>できなくなる</dt><dd>画像では見分けられない</dd></dl>
          </section>
        </div>
      </section>
    </details>

    <details class="sec" open>
      <summary class="sec-head"><h3 id="q2">Q2 カードの間隔</h3></summary>
      <section class="sec-body">
        <p><strong>前提:</strong> …</p>
        <doc-ask id="q2">
          <p>カードの間隔をいくつにするか</p>
          <label><input type="range" name="q2" min="8" max="24" step="4" value="12"> px (推奨 12)</label>
        </doc-ask>
      </section>
    </details>

  </section>
</details>
```

- 固定構成 (要点 → 用語 → 本論 → 詳細 → 根拠・出典) はそのまま。本論の h2 は「問い」の 1 つ、問いは h3 の `details.sec` で入れ子にする (runtime が h3 と `doc-ask` を左レールに拾う)
- `doc-ask` の `id` と `name` は問いの `id` (`q1` …)。radio の `value` は選択肢の `id`。推奨の選択肢に `checked` と `<small>推奨。<reason></small>`。選択肢に「その他」を置かない (別案はコメントで受ける)
- 選択肢のカードは `.cards` に 3 枚まで。4 枚目 (提案の案が足された問い) は 2 つ目の `.cards` に置く。カードの見出しは h4 (h3 にすると目次に出る)。`artboards` の無い選択肢も同じカードにし、`figure` を置かず得失だけを書く
- スクリーンショットは `figure.figure > img` に data URI で埋める (`.markdown-body img` が幅を収める)。`alt` と `figcaption` はアートボードの名前。`png: null` の案は `img` を置かず `p.note` にリンクと理由
- 1 案が複数のアートボード (複数画面) なら、カードの中に `figure` を続けて並べる
- 値の問いは `doc-ask` の `range` (目盛り) か radio (離散値)。推奨値を `value` / `checked` にする
- 答えは返信 (Respond) の `## Decisions` に、問いの行と `→` 行 (太字の選択肢の label と、続く選択肢の id) の形で、`kept as proposed` / `not opened; default kept` の区別つきで戻る (blocks.md 末尾)。読み方は `spec` Step 2 の規則

## diff 表示(diff)

CSS は同梱の `assets/style.css` に含まれている(`.file` `.file-head` `.hunk-head` `.diff-table` `.report-layout` `.file-nav` 等)。**この構造をそのまま使い、独自の diff スタイル(行番号なし・縞模様・1行ごとの隙間など)を発明しない** — 構造を即興にするとセッションごとに見た目が揺れ、行番号なしで読みにくい版・縞模様つきの版が混ざって出た実績がある。severity バッジ (`.sev-high` / `.sev-med` / `.sev-low`) は style.css に定義済み。追記は不要。

本文全体を `.report-layout` で包み、右側にファイル一覧ナビ(`.file-nav`)を出す。**ナビは手書きしない — ページ内の `details.file` を JS が document 順に自動走査して生成する**(手書きだとファイルの入れ忘れや本文とのズレが起きるため、生成は常に構造から導く)。

```html
<div class="report-layout">
  <div class="report-main">
    <!-- 既存のヘッダ・グループ見出しなどをここに書く -->
    <details class="file" open>
      <summary class="file-head">
        <span class="file-badge mod">変更</span>
        <span class="file-name">src/auth/session.ts</span>
        <mark class="sev-high">HIGH</mark>
        <span class="file-meta">
          <span class="hunk-count">5 hunks</span>
          <span class="stat-add">+21</span>
          <span class="stat-del">-7</span>
        </span>
      </summary>
      <div class="hunk">
        <div class="hunk-head">hunk 1/5 — @@ 3,7 → 3,7 @@ セッション検証の前後</div>
        <div class="diff-body">
          <table class="diff-table">
            <tbody>
              <tr class="diff-ctx"><td class="diff-ln-old">3</td><td class="diff-ln-new">3</td><td class="diff-code">  function validate(token) {</td></tr>
              <tr class="diff-del"><td class="diff-ln-old">4</td><td class="diff-ln-new"></td><td class="diff-code">-   if (!token) return true;</td></tr>
              <tr class="diff-add"><td class="diff-ln-old"></td><td class="diff-ln-new">4</td><td class="diff-code">+   if (!token) return false;</td></tr>
              <tr class="diff-ctx"><td class="diff-ln-old">5</td><td class="diff-ln-new">5</td><td class="diff-code">  }</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <!-- hunk 2/5 … 以降も同じ .hunk ブロックを繰り返す -->
      <p class="note">この変更が影響する挙動の説明(平易な言葉で)</p>
    </details>
    <!-- 2つ目以降の <details class="file"> … 同一ファイルが複数箇所に分かれて出てもよい -->
  </div>

  <aside class="file-nav" id="fileNav" aria-label="変更ファイル一覧">
    <p class="file-nav-head">ファイル一覧<span id="fileNavCount"></span></p>
    <noscript><p class="file-nav-noscript">JavaScript が無効なため一覧を生成できません。本文を直接確認してください。</p></noscript>
    <ul class="file-nav-list" id="fileNavList"></ul>
  </aside>
</div>

<script>
(function () {
  var files = Array.prototype.slice.call(document.querySelectorAll('details.file'));
  var list = document.getElementById('fileNavList');
  var countEl = document.getElementById('fileNavCount');
  if (!files.length || !list) return;

  files.forEach(function (file, i) {
    if (!file.id) file.id = 'file-' + (i + 1);

    var badge = file.querySelector('.file-badge');
    var type = badge && badge.classList.contains('new') ? 'new'
      : badge && badge.classList.contains('del') ? 'del' : 'mod';
    var nameEl = file.querySelector('.file-name');
    var nameText = nameEl ? nameEl.textContent.trim() : file.id;
    var addEl = file.querySelector('.stat-add');
    var delEl = file.querySelector('.stat-del');

    var a = document.createElement('a');
    a.href = '#' + file.id;

    var dot = document.createElement('span');
    dot.className = 'file-nav-dot ' + type;
    a.appendChild(dot);

    var nameSpan = document.createElement('span');
    nameSpan.className = 'file-nav-name';
    nameSpan.textContent = nameText;
    nameSpan.title = nameText;
    a.appendChild(nameSpan);

    if (addEl || delEl) {
      var meta = document.createElement('span');
      meta.className = 'file-nav-count';
      if (addEl) {
        var addSpan = document.createElement('span');
        addSpan.className = 'stat-add';
        addSpan.textContent = addEl.textContent.trim();
        meta.appendChild(addSpan);
      }
      if (delEl) {
        var delSpan = document.createElement('span');
        delSpan.className = 'stat-del';
        delSpan.textContent = delEl.textContent.trim();
        meta.appendChild(delSpan);
      }
      a.appendChild(meta);
    }

    a.addEventListener('click', function (e) {
      e.preventDefault();
      if (!file.open) file.open = true;   // 閉じたままだと高さがなく、飛び先がずれる
      file.scrollIntoView({ behavior: 'smooth', block: 'start' });
      // クリック直後は IntersectionObserver の発火を待たず即座にハイライトする
      // (末尾に近いファイルはスクロール余白が足りず observer 判定に入らないことがあるため)
      Array.prototype.forEach.call(list.querySelectorAll('a'), function (l) { l.classList.remove('active'); });
      a.classList.add('active');
    });

    var li = document.createElement('li');
    li.className = 'file-nav-item';
    li.appendChild(a);
    list.appendChild(li);
  });

  if (countEl) countEl.textContent = ' (' + files.length + ')';

  if ('IntersectionObserver' in window) {
    var links = Array.prototype.slice.call(list.querySelectorAll('a'));
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (l) { l.classList.remove('active'); });
        var link = list.querySelector('a[href="#' + entry.target.id + '"]');
        if (link) link.classList.add('active');
      });
    }, { rootMargin: '-15% 0px -75% 0px', threshold: 0 });
    files.forEach(function (file) { observer.observe(file); });
  }
})();
</script>
```

- `file-badge` は 変更=`mod` / 新規=`new` / 削除=`del` の3種。ファイル名は等幅(`file-name`)、右の `file-meta` に hunk 数と `+追加`(緑系)`-削除`(赤系)を置く
- diff 本体は必ずこの3列テーブル(旧行番号 / 新行番号 / コード)にする。行番号セルは選択不可(コピペでコードだけ拾えるように)。行の意味は `tr` のクラスで表す(`diff-add` / `diff-del` / `diff-ctx`)。**縞模様は付けない**
- diff 本文は HTML エスケープ必須(`<div>` や `&&` がそのまま出る)。色だけに頼らず `+` / `-` 記号もコード列に残す(色覚多様性への配慮)
- 重大度は HIGH / MED / LOW の3段。ファイル単位の `<details class="file">` は HIGH のみ `open`
- `.file-head` は `position: sticky` で常に画面上部に固定される(style.css で定義済み)。長い diff を下まで見た状態からでもその場で閉じられる
- **右のファイル一覧ナビは手書きしない**。上記スクリプトが `details.file` を document 順に走査し、id 採番・ファイル名・種別・`+N -M` をすべて本文から読み取って生成する。クリックすると対象が閉じていれば開いてからスクロールする(閉じたままだと高さがなくスクロール位置がずれるため)。表示中のファイルは `IntersectionObserver` で検出して `.active` を付ける
- 同一ファイルが複数の diff ブロックに分かれて登場するレポート(diff-review は意図単位でグループ分けするため起こりうる)では、ナビにも登場順のまま複数出てよい。1ファイル1エントリへ無理に統合しない
- 960px 以下ではナビが非表示になり1カラムに戻る(style.css のメディアクエリで対応済み)

## 図(縦フロー / 比較マトリクス / before-after / ツリー / タイムライン / 折れ線)

図の正本は `diagrams.md` に移した。「見せたいもの → 図の型」の対応表、5種のSVGテンプレの座標、日本語ラベルの幅の計算式、loop のスコア推移の折れ線と eval データの集計コマンドはすべてそちらにある。**このファイルには図を書かない** — 同じ図の正本が2つあると必ず乖離する。
