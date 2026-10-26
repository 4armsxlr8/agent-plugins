# 所要時間の文字列をコマンドラインから秒数に変換できるようにする

spec: docs/crystallize/specs/duration-cli.md

## 守るべき既存挙動
- `parse_duration` の解釈は変えない (tests/test_parse.py が依存)
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `durations/cli.py` に引数を秒数に変換して出力するコマンドを実装し、`python3 -m durations.cli` で実行できるようにする — AC-1〜AC-7 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: CLI (python3 -m durations.cli <所要時間の文字列>)

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
