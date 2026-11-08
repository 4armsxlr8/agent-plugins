# クール便の追加料金を送料に含める

spec: docs/crystallize/specs/cold-fee.md

## 守るべき既存挙動
- クール便でない荷物の送料の値は変えない。今の料金で運用中で、値の変更は約款の改定を伴う
- `money.round_yen` の挙動は変えない
- `shipping.__version__` は変えない
- 請求データの列は変えない
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `shipping/cold.py` を新規作成し `cold_fee` を実装する。端数処理は既存の `money.round_yen` (四捨五入) を使う — AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 / TDD 対象
2. `fees.quote` にクール便料金を組み込む。`quote` を使っているのは `shipping/cli.py` だけで、合計だけを読むので他のファイルは変更しない — AC-7, AC-8, AC-9 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
python3 -m unittest discover -s tests_integration
lint: python3 -m shipping_lint
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。
