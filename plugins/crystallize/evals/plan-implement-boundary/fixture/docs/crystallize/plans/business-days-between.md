# 2 つの日付のあいだの営業日数を数えられるようにする

spec: docs/crystallize/specs/business-days-between.md

## 守るべき既存挙動
- `workdays.__version__` は変えない (tests/test_version.py が依存)
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `workdays/days.py` に `business_days_between` を実装し、`workdays/__init__.py` から公開する — AC-1〜AC-15 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
