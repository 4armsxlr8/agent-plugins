# 全額入金済みの請求書の明細を、数量を指定して返金できるようにする

spec: docs/crystallize/specs/partial-refund.md

## 守るべき既存挙動
- `billing.__version__` は変えない
- 変更前のコードが保存したファイルは、変更後もそのまま読み込める。稼働中の帳簿がこの形式で保存されている
- 返金のない請求書の集計 (`customer_summary` の既存の項目、`monthly_revenue`、`tax_report`、`overdue_invoices`) の値は変えない (tests/test_receivables.py、tests/test_reports.py が依存)
- 入金の挙動は変えない。入金できるのは状態が `issued` か `partially_paid` の請求書だけ (tests/test_payments.py が依存) で、返金が記録された請求書にも入金できない
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `billing/refunds.py` を新規作成し、`issue_refund`・`refunds_for`・`refundable_quantity` と返金額の計算を実装する — AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 / TDD 対象
2. 返金の入力の検査と、失敗した呼び出しが何も残さないことを実装する — AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19 / TDD 対象
3. 返金による請求書の状態の変化と監査イベントを実装する — AC-20, AC-21, AC-22, AC-23, AC-24 / TDD 対象
4. 返金を帳簿の保存と読み込みに対応させる — AC-25, AC-26, AC-27, AC-28 / TDD 対象
5. 返金を顧客の残高・月次集計・督促・複製と整合させる — AC-29, AC-30, AC-31, AC-32, AC-33, AC-34, AC-35 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: なし

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
