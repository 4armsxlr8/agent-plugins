#!/bin/bash
# 作業ディレクトリに fixture を広げ、初期コミットを作る
set -euo pipefail
cp -R "$(dirname "$0")/fixture/." .
git init -q
git add -A
git -c user.name=eval -c user.email=eval@localhost commit -qm "initial"
