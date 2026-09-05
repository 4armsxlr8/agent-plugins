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
</head>
<body>
<button class="theme-toggle" id="themeToggle" type="button" aria-label="テーマ切り替え">◐</button>
<!-- <main> はどちらか一方を使う:
     散文レポート用 (html-report)      <main class="report markdown-body report-numbered">
     diff レポート用 (diff-review)     <main class="report report-numbered">
     diff 側で markdown-body を外すのは、`.markdown-body table` のような子孫セレクタ
     (詳細度 0,1,1) が diff-review 固有部品の単一 class (0,1,0) に勝ってしまうため。 -->
<main class="report markdown-body report-numbered">…</main>
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
</body>
</html>
```

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
- 目次を出すなら直後に `<nav class="report-toc">`。番号は CSS counter が振るので手で書かない

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
