# テキストの語数を数える関数と、ファイルの語数を表示するコマンドを用意する — core

spec: docs/crystallize/specs/word-count.md
covers: AC-1, AC-2, AC-3

## 守るべき既存挙動
- `wordcount.__version__` は変えない (tests/test_version.py が依存)
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `wordcount/count.py` を新規作成して `count_words` を実装し、`wordcount/__init__.py` から公開する — AC-1, AC-2, AC-3 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
