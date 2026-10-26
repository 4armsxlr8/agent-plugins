# 所要時間の文字列で秒 (`s`) を書けるようにする

spec: docs/crystallize/specs/seconds-unit.md

## 守るべき既存挙動
- 単位のない数字は分として扱う。`durations/cli.py` の `--timeout` が依存しており、既存の設定ファイルは `--timeout 30` (= 30 分) の形で書かれている。移行手段は用意しない
- tests/test_parse.py の既存テストはそのまま通す

## 実装計画 (変わりやすい順)
1. `durations/parse.py` の `parse_duration` に単位 `s` を追加する — AC-1〜AC-4 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
