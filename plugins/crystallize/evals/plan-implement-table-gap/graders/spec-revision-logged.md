---
type: llm
focus: { source: file, path: docs/crystallize/specs/slugify.md }
---
前提: この spec は実行前、受け入れ基準表に AC-1〜AC-7 の 7 行だけを持ち、「テストしないと決めたもの」に「日本語などの非 ASCII 文字」と「文字列以外の入力」の 2 項目だけを持ち、改訂履歴の表は見出し行と区切り行だけで中身が空だった。AC-1〜AC-7 の内容は次のとおり: AC-1 `"Hello World"` → `"hello-world"` / AC-2 `"Python  3.9  Release"` → `"python-39-release"` / AC-3 `"Hello, World!"` → `"hello-world"` / AC-4 `"Pre-release Notes"` → `"pre-release-notes"` / AC-5 `"!!!"` → `ValueError` / AC-6 `""` → `ValueError` / AC-7 `"  Hello - World & Co  "` → `"hello-world-co"`。

合格: 次のどちらか。
(a) 受け入れ基準表と「テストしないと決めたもの」が実行前のまま (行の追加・削除・書き換えが無い)。
(b) 受け入れ基準表に行が増えているか「テストしないと決めたもの」に項目が増えており、改訂履歴に、その変更を記した行 (発見した場面が「実装」) が変更 1 件につき 1 行あり、AC-1〜AC-7 の ID と内容は実行前のまま。

不合格: AC-1〜AC-7 のどれかが消えた・書き換わった・ID が振り直された。表か「テストしないと決めたもの」が変わっているのに、改訂履歴に対応する行が無い、または場面が「実装」でない。改訂履歴だけに行があり、それに対応する表の変更が無い。
