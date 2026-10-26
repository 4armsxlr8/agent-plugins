# スコアの上位 n 件を、元の一覧を崩さずに取り出せるようにする

spec: docs/crystallize/specs/top-n.md

## 守るべき既存挙動
- `leaderboard` は渡された list をその場でスコアの降順に並べ替えて返す。画面側が同じ list を使い回しており、tests/test_leaderboard.py が依存している
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `ranking/scores.py` に `top_n` を実装し、`ranking/__init__.py` から公開する — AC-1〜AC-8 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
