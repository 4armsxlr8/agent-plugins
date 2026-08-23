# 調整パネル (tweak panel) — 正本仕様

Step 2 の反応用モックに埋め込む調整パネルの**唯一の正本**。SKILL.md 側にはポインタだけを置き、パネルの見た目・操作・コピー/取り込みの契約はすべて本ファイルで定義する。モック作成サブエージェントには本ファイルのパスを渡し、テンプレートを**無改変で**埋め込ませる。

## なぜ正本を固定するか

モックごとにパネルを自作させると、案ごと・セッションごとに UI と JSON 形式がばらける。ばらけたパネルは (1) ユーザーが案を行き来するたびに操作を学び直す、(2) 案 A で調整した値を案 B に持ち込めない、(3) 親が反応を ledger に転記する形式が毎回変わる — の3点で認識合わせを遅らせる。

## 一貫性の2軸 (担保する場所が違う)

| 軸 | 内容 | 担保する場所 |
|---|---|---|
| 構造の一貫性 | パネルの見た目・操作・JSON 形式が全モック・全セッションで同じ | 本ファイルのテンプレート (無改変で埋め込む) |
| タスク内の一貫性 | 同一タスクの複数案で、同じプロパティに同じキー・同じ range・同じ単位 | **親の指示** — 親が TWEAKS キー一覧 (キー名・型・range・単位・初期値) を先に決め、全モック作成サブエージェントに**同一のものを**渡す |

テンプレートだけではタスク内の一貫性は担保されない — キー一覧を各サブエージェントに任せると、パネルは個々に綺麗でも互いに比較不能になる。

## 契約

- **`TWEAKS` 設定オブジェクト**: パネルはこの宣言だけから自動生成される。コントロールの markup を手書きしない
  - `{ key: { label, type, value, min, max, step, unit, options } }`
  - `type` は `range` | `number` | `color` | `select` の4種。`options` は `select` のみ (`[{value, label}]`)
  - キー名は lowerCamelCase の挙動語彙 (例: `cardGap`, `accentColor`, `itemCount`)
- **`applyTweaks(values)`**: モック側が実装する唯一の接続点。flat な `{key: value}` を受け取りモックの DOM / スタイルに反映する。初期表示時にも1回呼ばれる
- **JSON 契約**: flat な `{key: value}` のみ。ネスト・メタ情報を入れない。「設定をコピー」は `navigator.clipboard` へ書き、**同じ JSON をパネル内のテキスト欄にも常時表示**する (clipboard が使えない環境のフォールバック)。同じテキスト欄に JSON を貼って「取り込み」を押すと値が適用される (案間の値の持ち運び用 — 案 A で決めた値を案 B に貼って見比べる)
- **スタイル隔離**: パネルはモックのデザイン評価を汚染してはならない
  - `position: fixed` 右下・高 z-index・折りたたみ可能
  - class は全て `cz-tweak-` プレフィックス。素の要素セレクタ (`button {…}` 等) を書かない
  - 配色はモックのデザイン方向と無関係なニュートラルな「ツールの見た目」に固定する

## 埋め込み手順 (モック作成サブエージェント向け)

1. 下のテンプレートを `<body>` 末尾に**無改変で**貼る
2. `TWEAKS` を、親から渡されたキー一覧**どおりに**定義する (勝手にキーを増減・改名しない。追加したい調整項目があれば親に返して全案へ同時に反映してもらう)
3. `applyTweaks(values)` を自分のモックに合わせて実装する
4. 変えてよいのは `TWEAKS` の定義と `applyTweaks` の中身だけ。テンプレート本体 (markup・CSS・パネル生成 JS) には手を入れない

## テンプレート

<!-- TEMPLATE:BEGIN -->
```html
<!-- ここから下がモックごとに書く部分 -->
<script>
  // (a) TWEAKS 定義例 — 親から渡されたキー一覧どおりに書き換える。
  // type は 'range' | 'number' | 'color' | 'select' の4種。
  const TWEAKS = {
    itemGap: { label: '間隔', type: 'range', value: 16, min: 0, max: 48, step: 1, unit: 'px' }
    // 例) accentColor: { label: '色', type: 'color', value: '#5b8def' }
    // 例) itemCount:   { label: '件数', type: 'number', value: 8, min: 1, max: 40, step: 1, unit: '件' }
    // 例) layout:      { label: 'レイアウト', type: 'select', value: 'grid',
    //       options: [{ value: 'grid', label: 'グリッド' }, { value: 'list', label: 'リスト' }] }
  };

  // (b) applyTweaks はモックごとに実装するスタブ。TWEAKS の全キーを含む flat な値一式を受け取る。
  function applyTweaks(values) {
    // ここにモックへ反映する処理を書く
    // 例: document.documentElement.style.setProperty('--item-gap', values.itemGap + 'px');
  }
</script>

<!-- ここから下は無改変で埋め込む (正本: tweak-panel.md) -->
<div id="cz-tweak-panel" class="cz-tweak-panel">
  <button type="button" id="cz-tweak-pill-btn" class="cz-tweak-pill" aria-label="調整パネルを開く">⚙ 調整</button>
  <div class="cz-tweak-inner">
    <div class="cz-tweak-header">
      <span class="cz-tweak-title">調整パネル</span>
      <button type="button" id="cz-tweak-collapse-btn" class="cz-tweak-collapse-btn" aria-label="折りたたむ">─</button>
    </div>
    <div class="cz-tweak-body">
      <div class="cz-tweak-controls" id="cz-tweak-controls"></div>
      <div class="cz-tweak-json-block">
        <div class="cz-tweak-json-heading">JSON (コピー / 取り込み)</div>
        <textarea id="cz-tweak-json" class="cz-tweak-json-area" spellcheck="false" rows="6"></textarea>
        <div class="cz-tweak-actions">
          <button type="button" id="cz-tweak-import-btn" class="cz-tweak-action-btn">取り込み</button>
          <button type="button" id="cz-tweak-copy-btn" class="cz-tweak-action-btn">設定をコピー</button>
        </div>
        <div id="cz-tweak-feedback" class="cz-tweak-feedback"></div>
      </div>
    </div>
  </div>
</div>
<style>
  /* リセット: モック側の CSS に負けないよう主要プロパティを明示指定して防御する */
  .cz-tweak-panel,
  .cz-tweak-panel *,
  .cz-tweak-panel *::before,
  .cz-tweak-panel *::after {
    box-sizing: border-box !important;
  }
  .cz-tweak-panel,
  .cz-tweak-panel * {
    margin: 0;
    padding: 0;
    border: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
    font-size: 12px;
    line-height: 1.5;
    color: #e6e6ea;
    text-align: left;
    background: none;
    letter-spacing: normal;
    text-shadow: none;
    box-shadow: none;
  }
  .cz-tweak-panel {
    position: fixed !important;
    right: 16px !important;
    bottom: 16px !important;
    z-index: 99999 !important;
  }
  .cz-tweak-pill {
    display: none;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    background: #24262b !important;
    border: 1px solid #454951 !important;
    border-radius: 999px !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35) !important;
    color: #e6e6ea !important;
    font-weight: 600 !important;
    cursor: pointer;
  }
  .cz-tweak-panel.cz-tweak-collapsed .cz-tweak-pill {
    display: inline-flex;
  }
  .cz-tweak-panel.cz-tweak-collapsed .cz-tweak-inner {
    display: none;
  }
  .cz-tweak-inner {
    display: flex;
    flex-direction: column;
    width: 264px;
    max-width: calc(100vw - 32px);
    max-height: 70vh;
    background: #24262b !important;
    border: 1px solid #3a3d44 !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
    overflow: hidden;
  }
  .cz-tweak-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    background: #2b2e34 !important;
    border-bottom: 1px solid #3a3d44 !important;
    flex: 0 0 auto;
  }
  .cz-tweak-title {
    font-weight: 700 !important;
    color: #f1f1f4 !important;
  }
  .cz-tweak-collapse-btn {
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #35383f !important;
    border: 1px solid #454951 !important;
    border-radius: 6px !important;
    color: #e6e6ea !important;
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
  }
  .cz-tweak-body {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    padding: 10px 12px 12px;
  }
  .cz-tweak-controls {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .cz-tweak-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .cz-tweak-row-top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }
  .cz-tweak-label {
    color: #b7bac2 !important;
    font-size: 11px;
  }
  .cz-tweak-value {
    color: #f1f1f4 !important;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .cz-tweak-input {
    width: 100%;
    display: block;
    background: #1a1c20 !important;
    border: 1px solid #454951 !important;
    border-radius: 6px !important;
    color: #e6e6ea !important;
  }
  .cz-tweak-input-range {
    height: 18px;
    padding: 0;
    background: transparent !important;
    border: 0 !important;
    -webkit-appearance: none;
    appearance: none;
  }
  .cz-tweak-input-range::-webkit-slider-runnable-track {
    height: 4px;
    background: #454951 !important;
    border-radius: 2px !important;
  }
  .cz-tweak-input-range::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    margin-top: -5px;
    border-radius: 50% !important;
    background: #d7d9de !important;
    border: 1px solid #8f939c !important;
    cursor: pointer;
  }
  .cz-tweak-input-range::-moz-range-track {
    height: 4px;
    background: #454951 !important;
    border-radius: 2px !important;
  }
  .cz-tweak-input-range::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50% !important;
    background: #d7d9de !important;
    border: 1px solid #8f939c !important;
    cursor: pointer;
  }
  .cz-tweak-input-number {
    height: 26px;
    padding: 0 8px;
  }
  .cz-tweak-input-color {
    height: 26px;
    padding: 2px;
    cursor: pointer;
  }
  .cz-tweak-select {
    height: 26px;
    padding: 0 6px;
    background: #1a1c20 !important;
    border: 1px solid #454951 !important;
    border-radius: 6px !important;
    color: #e6e6ea !important;
    cursor: pointer;
  }
  .cz-tweak-json-block {
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid #3a3d44 !important;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .cz-tweak-json-heading {
    font-size: 11px;
    font-weight: 700 !important;
    color: #b7bac2 !important;
  }
  .cz-tweak-json-area {
    width: 100%;
    min-height: 96px;
    resize: vertical;
    background: #1a1c20 !important;
    border: 1px solid #454951 !important;
    border-radius: 6px !important;
    color: #e6e6ea !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
    font-size: 11px;
    padding: 6px 8px;
    white-space: pre;
  }
  .cz-tweak-actions {
    display: flex;
    gap: 8px;
  }
  .cz-tweak-action-btn {
    flex: 1 1 auto;
    height: 28px;
    background: #35383f !important;
    border: 1px solid #4a4e56 !important;
    border-radius: 6px !important;
    color: #f1f1f4 !important;
    font-weight: 600 !important;
    font-size: 11px;
    cursor: pointer;
  }
  .cz-tweak-action-btn:hover {
    background: #40444c !important;
  }
  .cz-tweak-action-btn:active {
    background: #2c2f34 !important;
  }
  .cz-tweak-feedback {
    min-height: 14px;
    font-size: 10.5px;
  }
  .cz-tweak-feedback--ok {
    color: #8bc98f !important;
  }
  .cz-tweak-feedback--error {
    color: #ff9c92 !important;
  }
</style>
<script>
  (function () {
    'use strict';

    var panelEl = document.getElementById('cz-tweak-panel');
    if (!panelEl || typeof TWEAKS === 'undefined' || typeof applyTweaks !== 'function') return;

    var controlsEl = document.getElementById('cz-tweak-controls');
    var jsonArea = document.getElementById('cz-tweak-json');
    var importBtn = document.getElementById('cz-tweak-import-btn');
    var copyBtn = document.getElementById('cz-tweak-copy-btn');
    var feedbackEl = document.getElementById('cz-tweak-feedback');
    var collapseBtn = document.getElementById('cz-tweak-collapse-btn');
    var pillBtn = document.getElementById('cz-tweak-pill-btn');

    var keys = Object.keys(TWEAKS);
    var state = {};
    keys.forEach(function (key) {
      state[key] = TWEAKS[key].value;
    });

    // 数値系(type: range/number)は数値へ丸めて min/max を尊重、それ以外(color/select)は文字列のまま返す
    function coerce(key, raw) {
      var cfg = TWEAKS[key];
      if (cfg.type === 'range' || cfg.type === 'number') {
        var n = parseFloat(raw);
        if (isNaN(n)) return state[key];
        if (cfg.min !== undefined) n = Math.max(cfg.min, n);
        if (cfg.max !== undefined) n = Math.min(cfg.max, n);
        return n;
      }
      return raw;
    }

    // ラベル横の「現在値 + unit」表示を組み立てる
    function formatValue(key) {
      var cfg = TWEAKS[key];
      var v = state[key];
      if (cfg.type === 'select') {
        var found = null;
        (cfg.options || []).forEach(function (opt) {
          if (opt.value === v) found = opt;
        });
        return found ? found.label : String(v);
      }
      if (cfg.type === 'color') {
        return String(v);
      }
      return String(v) + (cfg.unit || '');
    }

    function refreshRowUI(key) {
      var valueEl = document.getElementById('cz-tweak-value-' + key);
      if (valueEl) valueEl.textContent = formatValue(key);
      var fieldEl = document.getElementById('cz-tweak-field-' + key);
      // 入力中のフィールドへは書き戻さない (書き戻すと数値入力を空にできない・キャレットが飛ぶ)
      if (fieldEl && document.activeElement !== fieldEl) fieldEl.value = state[key];
    }

    function syncJson() {
      jsonArea.value = JSON.stringify(state, null, 2);
    }

    function notify(message, isError) {
      feedbackEl.textContent = message;
      feedbackEl.className = 'cz-tweak-feedback ' + (isError ? 'cz-tweak-feedback--error' : 'cz-tweak-feedback--ok');
    }

    // 値変更のたびに JSON 欄を更新し applyTweaks を呼ぶ唯一の入口
    function commit() {
      syncJson();
      try {
        applyTweaks(Object.assign({}, state));
      } catch (e) {
        notify('applyTweaks でエラー: ' + e.message, true);
      }
    }

    function buildControls() {
      keys.forEach(function (key) {
        var cfg = TWEAKS[key];

        var row = document.createElement('div');
        row.className = 'cz-tweak-row';

        var top = document.createElement('div');
        top.className = 'cz-tweak-row-top';

        var label = document.createElement('label');
        label.className = 'cz-tweak-label';
        label.setAttribute('for', 'cz-tweak-field-' + key);
        label.textContent = cfg.label || key;

        var valueSpan = document.createElement('span');
        valueSpan.className = 'cz-tweak-value';
        valueSpan.id = 'cz-tweak-value-' + key;

        top.appendChild(label);
        top.appendChild(valueSpan);
        row.appendChild(top);

        var field;
        if (cfg.type === 'select') {
          field = document.createElement('select');
          field.className = 'cz-tweak-input cz-tweak-select';
          (cfg.options || []).forEach(function (opt) {
            var o = document.createElement('option');
            o.value = opt.value;
            o.textContent = opt.label;
            field.appendChild(o);
          });
        } else if (cfg.type === 'color') {
          field = document.createElement('input');
          field.type = 'color';
          field.className = 'cz-tweak-input cz-tweak-input-color';
        } else if (cfg.type === 'number') {
          field = document.createElement('input');
          field.type = 'number';
          field.className = 'cz-tweak-input cz-tweak-input-number';
          if (cfg.min !== undefined) field.min = cfg.min;
          if (cfg.max !== undefined) field.max = cfg.max;
          if (cfg.step !== undefined) field.step = cfg.step;
        } else {
          // 既定は range
          field = document.createElement('input');
          field.type = 'range';
          field.className = 'cz-tweak-input cz-tweak-input-range';
          if (cfg.min !== undefined) field.min = cfg.min;
          if (cfg.max !== undefined) field.max = cfg.max;
          if (cfg.step !== undefined) field.step = cfg.step;
        }
        field.id = 'cz-tweak-field-' + key;
        field.value = cfg.value;

        field.addEventListener('input', function () {
          state[key] = coerce(key, field.value);
          refreshRowUI(key);
          commit();
        });
        // フォーカスが外れたら min/max で丸められた確定値を表示に反映する
        field.addEventListener('blur', function () {
          refreshRowUI(key);
        });

        row.appendChild(field);
        controlsEl.appendChild(row);
        refreshRowUI(key);
      });
    }

    function applyImport() {
      var parsed;
      try {
        parsed = JSON.parse(jsonArea.value);
      } catch (e) {
        notify('JSON の形式が正しくありません: ' + e.message, true);
        return;
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        notify('JSON はオブジェクト形式である必要があります', true);
        return;
      }

      var unknown = [];
      var invalid = [];

      Object.keys(parsed).forEach(function (key) {
        if (keys.indexOf(key) === -1) {
          unknown.push(key);
          return;
        }
        var cfg = TWEAKS[key];
        var value = parsed[key];

        if (cfg.type === 'range' || cfg.type === 'number') {
          var n = Number(value);
          if (value === null || value === '' || isNaN(n)) {
            invalid.push(key);
            return;
          }
          if (cfg.min !== undefined) n = Math.max(cfg.min, n);
          if (cfg.max !== undefined) n = Math.min(cfg.max, n);
          state[key] = n;
        } else if (cfg.type === 'color') {
          if (typeof value !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(value)) {
            invalid.push(key);
            return;
          }
          state[key] = value;
        } else if (cfg.type === 'select') {
          var isValid = false;
          (cfg.options || []).forEach(function (opt) {
            if (opt.value === value) isValid = true;
          });
          if (typeof value !== 'string' || !isValid) {
            invalid.push(key);
            return;
          }
          state[key] = value;
        }
        refreshRowUI(key);
      });

      commit();

      var messages = [];
      if (unknown.length) messages.push('未知のキーは無視しました: ' + unknown.join(', '));
      if (invalid.length) messages.push('不正な値は無視しました: ' + invalid.join(', '));
      if (messages.length) {
        notify(messages.join(' / '), true);
      } else {
        notify('取り込みました', false);
      }
    }

    function copyConfig() {
      var text = JSON.stringify(state, null, 2);
      try {
        navigator.clipboard.writeText(text).then(
          function () {
            notify('コピーしました', false);
          },
          function () {
            notify('コピーに失敗しました。下の欄からコピーしてください', true);
          }
        );
      } catch (e) {
        notify('コピーに失敗しました。下の欄からコピーしてください', true);
      }
    }

    function setCollapsed(collapsed) {
      panelEl.classList.toggle('cz-tweak-collapsed', collapsed);
    }

    buildControls();
    importBtn.addEventListener('click', applyImport);
    copyBtn.addEventListener('click', copyConfig);
    collapseBtn.addEventListener('click', function () {
      setCollapsed(true);
    });
    pillBtn.addEventListener('click', function () {
      setCollapsed(false);
    });

    commit(); // 初期表示でも1回 applyTweaks を呼ぶ
  })();
</script>
```
<!-- TEMPLATE:END -->
