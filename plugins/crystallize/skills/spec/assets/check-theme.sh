#!/bin/sh
# 配色の変数が html-report の style.css と一致するかの検算 (プラグインリポジトリで定義ファイルを編集したときに実行する保守用)。
# 使い方: sh check-theme.sh   (このファイルの場所から正本を探す)
set -u
D=$(cd "$(dirname "$0")" && pwd)
CSS="$D/../../html-report/assets/style.css"; ok=0
for f in "$D/doc-sheet.html" "$D/mock-kit.html"; do
  for b in LIGHT DARK; do
    a=$(sed -n "/CZ-THEME:$b:BEGIN/,/CZ-THEME:$b:END/p" "$CSS" | sed '1d;$d' | shasum | cut -d' ' -f1)
    m=$(sed -n "/CZ-THEME:$b:BEGIN/,/CZ-THEME:$b:END/p" "$f"   | sed '1d;$d' | shasum | cut -d' ' -f1)
    if [ "$a" = "$m" ]; then echo "$(basename "$f") $b: 一致"; else echo "$(basename "$f") $b: style.css と違う"; ok=1; fi
  done
done
[ $ok -eq 0 ] && echo "配色: すべて一致" || echo "配色: 不一致あり"
exit $ok
