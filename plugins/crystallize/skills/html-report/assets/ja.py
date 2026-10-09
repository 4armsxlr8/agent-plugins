#!/usr/bin/env python3
"""htmlplan.js の画面の文言を日本語にする (保守用)。

上流 (anthropics/claude-plugins-community の html-plan) を取り込み直したら、
runtime/htmlplan.js を assets/htmlplan.js に上書きしてからこれを 1 回実行する:

    python3 assets/ja.py

置き換えるのは読者が画面で見るボタン・見出し・ヒントだけ。Respond が出す markdown
(## Decisions / kept as proposed …) は Claude が読む側の文なので英語のまま。
置換元が見つからない行があれば、上流で文言が変わったので止めて知らせる。
"""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
JS = HERE / 'htmlplan.js'

NOTE = ("/* 出自: https://github.com/anthropics/claude-plugins-community/tree/main/html-plan (skills/html-plan/runtime/htmlplan.js)\n"
        "   作者 Thariq Shihipar。plugin.json は MIT、リポジトリの LICENSE は Apache-2.0。\n"
        "   変更は assets/ja.py による画面の文言の日本語化のみ (ロジックは無改変)。見た目の調整は style.css 側で行う。\n"
        "   html-report は pack.mjs を使わない (src=/lines=/ref= は埋まらない)。コードは <script type=\"text/plain\"> に貼る。 */\n")

# (置換元, 置換先)。置換元は上流の文字列そのまま。順番に意味はない
REPL = [
    # 右下のバー
    ("}, 'Respond'));", "}, '返信'));"),
    ("btn.append(r.nAsks || n ? 'Respond' : 'Comment',", "btn.append(r.nAsks || n ? '返信' : 'コメント',"),
    ("nx.textContent = `${nTodo} to answer ↓`;", "nx.textContent = `未回答 ${nTodo} ↓`;"),
    ("title: 'Go to the next decision'", "title: '次の決定へ'"),
    ("title: 'Contents', onclick: () => openSheet('Contents', tocMk())", "title: '目次', onclick: () => openSheet('目次', tocMk())"),
    # 返信シート
    ("openSheet('Your response', [list, h('p', { class: 'hint' }, liveOn ? 'This goes to Claude when you press Send.' : 'Copy this and paste it to Claude.'), pre]",
     "openSheet('返信', [list, h('p', { class: 'hint' }, liveOn ? '送信を押すと Claude に届きます。' : 'コピーして Claude のチャットに貼ってください。'), pre]"),
    ("h('div', { class: 'ttl' }, 'Decisions', h('b', { class: nTodo ? 'todo' : '' }, nTodo ? `${nTodo} to answer` : 'all answered'))",
     "h('div', { class: 'ttl' }, '決定', h('b', { class: nTodo ? 'todo' : '' }, nTodo ? `未回答 ${nTodo}` : 'すべて回答済み'))"),
    ("st === 'todo' ? 'to answer' : st === 'kept' ? 'as proposed' : 'changed'", "st === 'todo' ? '未回答' : st === 'kept' ? '提案どおり' : '変更あり'"),
    ("toast('Copied — paste it back to Claude')", "toast('コピーしました — Claude に貼ってください')"),
    ("toast('Copied'); } } }, 'Copy response');", "toast('コピーしました'); } } }, '返信をコピー');"),
    ("reset.textContent = 'Clear everything?';", "reset.textContent = 'すべて消しますか?';"),
    ("reset.textContent = 'Reset'; }, 3000)", "reset.textContent = 'リセット'; }, 3000)"),
    ("toast('Reset'); } }, 'Reset');", "toast('リセットしました'); } }, 'リセット');"),
    ("h('button', { class: 'nw-btn', onclick: closeSheet }, 'Close')", "h('button', { class: 'nw-btn', onclick: closeSheet }, '閉じる')"),
    ("ask.dataset.n = `${kd[0].toUpperCase() + kd.slice(1)} ${i + 1} of ${asks.length}`",
     "ask.dataset.n = `${kd === 'decision' ? '決定' : kd} ${i + 1} / ${asks.length}`"),
    # コメントの吹き出し
    ("placeholder: 'Comment for Claude…'", "placeholder: 'Claude へのコメント…'"),
    ("}, 'Remove');", "}, '削除');"),
    ("h('button', { class: 'nw-btn', onclick: closePop }, 'Cancel')", "h('button', { class: 'nw-btn', onclick: closePop }, 'キャンセル')"),
    ("save(); closePop(); } }, 'Save')));", "save(); closePop(); } }, '保存')));"),
    ("title: 'Comment', 'aria-label': 'Comment'", "title: 'コメント', 'aria-label': 'コメント'"),
    ("tdLn.title = 'Comment on this line';", "tdLn.title = 'この行にコメント';"),
    # 目次
    ("h('div', { class: 'ttl' }, 'Contents')", "h('div', { class: 'ttl' }, '目次')"),
    # doc-ask / doc-changes
    ("h('span', { class: 'sug' }, 'Suggested')", "h('span', { class: 'sug' }, '推奨')"),
    ("}, 'Proposed')", "}, '提案')"),
    # doc-schema / doc-draft の編集
    ("btnEdit.textContent = editing ? 'Done' : 'Edit';", "btnEdit.textContent = editing ? '完了' : '編集';"),
    ("'✎ edited — diff goes in your response'", "'✎ 編集済み — diff が返信に入ります'"),
    ("}, 'Revert')", "}, '元に戻す')"),
    # doc-calls の打ち消し
    ("self ? 'restore' : '⊘ strike'", "self ? '戻す' : '⊘ 打ち消す'"),
    ("'✎ comment'", "'✎ コメント'"),
    # doc-machine
    ("'Tap a state to see its screen'", "'状態をタップすると、その画面が出ます'"),
    ("'Tap a state'", "'状態をタップ'"),
    # 図
    ("title: 'View full size', 'aria-label': 'View full size'", "title: '原寸で見る', 'aria-label': '原寸で見る'"),
    ("style: 'display:block', onclick: () => openSheet('Contents', tocMk())", "style: 'display:block', onclick: () => openSheet('目次', tocMk())"),
]

src = JS.read_text()
if src.startswith('/* 出自:'):
    src = src[src.index('*/\n') + 3:]   # 前回の注記を外してから付け直す
missing = [a for a, b in REPL if src.count(a) == 0 and src.count(b) == 0]   # 置換済み (b がある) なら通す: 2 回実行しても壊れない
if missing:
    print('上流の文言が変わっています。置換元が見つからない:', *missing, sep='\n  ')
    sys.exit(1)
for a, b in REPL:
    src = src.replace(a, b)
JS.write_text(NOTE + src)
print('ok', JS, len(REPL), 'replacements')
