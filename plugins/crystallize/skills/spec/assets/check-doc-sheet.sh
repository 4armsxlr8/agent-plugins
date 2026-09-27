#!/bin/sh
# 文書シートの検算。使い方: sh check-doc-sheet.sh [--dump] <正本 doc-sheet.html> <作った sheet.html>
# 1) 無改変層 3 ブロックが正本と一致するか  2) スロット層の宣言があるか  3) スロット層の構文
# 4) MODEL / exhibit / VALUE_EXHIBITS を、値 (既定・最小・最大) × 答え (推奨、および各問いで他の選択肢を 1 つずつ選んだ状態) で実際に呼び、
#    例外なく table / text のブロックが返るか。--dump を付けると既定値・推奨で描いた見るものの中身を文字で出す (試問に渡す)
set -u
DUMP=0; if [ "${1:-}" = "--dump" ]; then DUMP=1; shift; fi
KIT="$1"; SHEET="$2"; ok=0
for b in STYLE MARKUP SCRIPT; do
  a=$(sed -n "/CZ-DOC:$b:BEGIN/,/CZ-DOC:$b:END/p" "$KIT"   | shasum | cut -d' ' -f1)
  m=$(sed -n "/CZ-DOC:$b:BEGIN/,/CZ-DOC:$b:END/p" "$SHEET" | shasum | cut -d' ' -f1)
  if [ "$a" = "$m" ]; then echo "$b: 一致"; else echo "$b: 改変あり"; ok=1; fi
done
for d in 'const ROUND\b' 'const QUESTIONS\b' 'const DECIDED\b' 'MODEL\b'; do
  if grep -q "^\(const \|function \)\{0,1\}$d" "$SHEET" 2>/dev/null || grep -q "^$d" "$SHEET"; then :; else echo "宣言が無い: $d"; ok=1; fi
done
DATA="${TMPDIR:-/tmp}/cz-data.$$.js"
awk '/^<script id="cz-doc-data">/{f=1;next} /^<\/script>/{f=0} f' "$SHEET" > "$DATA"
node --check "$DATA" || ok=1
DUMP=$DUMP node -e '
const vm = require("vm"), fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8") + "\n;({ ROUND, PREMISES, TWEAKS, QUESTIONS, DECIDED, MODEL, VALUE_EXHIBITS })";
const d = new vm.Script(src).runInNewContext({ console });
const qs = [...d.DECIDED, ...d.QUESTIONS];
const pickWith = over => id => { if (id in over) return over[id]; const q = qs.find(q => q.id === id); return q ? (q.decided || q.recommended) : undefined; };
// 答えの組: 推奨のまま + 各問いで不採用でない他の選択肢を 1 つずつ選んだ状態
const answerSets = [["推奨", {}]];
d.QUESTIONS.forEach(q => (q.options || []).forEach(o => { if (!o.rejected && o.id !== q.recommended) answerSets.push([q.id + "=" + o.id, { [q.id]: o.id }]); }));
const valueSets = { "既定値": t => t.value, "最小値": t => t.min, "最大値": t => t.max };
const dump = [];
for (const [vname, f] of Object.entries(valueSets)) for (const [aname, over] of answerSets) {
  const vals = {}; d.TWEAKS.forEach(t => { vals[t.key] = f(t); });
  const pick = pickWith(over);
  const m = d.MODEL(vals, pick); let n = 0;
  const run = (fn, where) => [].concat(fn(m, vals, pick) || []).forEach(b => {
    if (!b || (b.type !== "table" && b.type !== "text")) throw new Error(where + ": type が table / text ではない");
    if (b.type === "table" && (!Array.isArray(b.columns) || !Array.isArray(b.rows))) throw new Error(where + ": table に columns / rows が無い");
    (b.uses || []).forEach(k => { if (!d.TWEAKS.some(t => t.key === k)) throw new Error(where + ": uses の " + k + " は TWEAKS に無い"); });
    n++;
    if (vname === "既定値" && aname === "推奨") dump.push("## " + where + (b.title ? " — " + b.title : ""),
      b.type === "table" ? [b.columns.join(" | "), ...b.rows.map(r => r.join(" | "))].join("\n") : String(b.text), b.note ? "(注記) " + b.note : "");
  });
  qs.forEach(q => { if (q.exhibit) run(q.exhibit, q.id); (q.options || []).forEach(o => o.exhibit && run(o.exhibit, q.id + "/" + o.id)); });
  run(d.VALUE_EXHIBITS, "VALUE_EXHIBITS");
  if (aname === "推奨") console.log(vname + ": 見るもの " + n + " ブロックを描けました");
}
console.log("答えの組 " + answerSets.length + " 通り × 値 3 通りで例外なし");
const ids = d.QUESTIONS.map(q => q.id), dup = ids.filter((x, i) => ids.indexOf(x) !== i);
if (dup.length) throw new Error("QUESTIONS の id が重複: " + dup.join(","));
const both = d.DECIDED.map(q => q.id).filter(id => ids.includes(id));
if (both.length) throw new Error("DECIDED と QUESTIONS に同じ id: " + both.join(",") + " (問い直す問いは QUESTIONS に残す)");
if (process.env.DUMP === "1") console.log("\n# 見るもの (既定値・推奨)\n" + dump.filter(Boolean).join("\n"));
' "$DATA" || ok=1
rm -f "$DATA"
[ $ok -eq 0 ] && echo "検算: すべて通過" || echo "検算: 不合格あり"
exit $ok
