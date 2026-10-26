# 秒数を「1h30m」のような所要時間の文字列に戻せるようにする

spec: docs/crystallize/specs/format-duration.md

## 守るべき既存挙動
- `parse_duration` の挙動は変えない (tests/test_parse.py が依存)
- `durations.__version__` は変えない (tests/test_version.py が依存)
- README.md の「使い方」節にある既存の `parse_duration` の例は残す
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `durations/format.py` に `format_duration` を実装し、`durations/__init__.py` から公開する — AC-1〜AC-10 / TDD 対象
2. `README.md` の「使い方」節に `format_duration` の使用例を足す — AC-11 / TDD 対象外

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
