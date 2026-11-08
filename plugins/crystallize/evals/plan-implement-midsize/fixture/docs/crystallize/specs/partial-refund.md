# 全額入金済みの請求書の明細を、数量を指定して返金できるようにする

## 使う人と場面
- ジョブストーリー: 顧客が商品の一部を返品してきたとき、請求書を取り消さずに返品された数量の分だけ返金を記録したい。そうすれば売上・税額・顧客の残高の集計が帳簿と合ったままになる
- 使う人: このライブラリを使う経理システムの開発者 / 場面: 入金済みの請求書に対する返品を処理している / やり遂げたいこと: 返金を記録し、集計に反映する / 今のやり方: 表計算で返金を別管理し、月末に集計値を手で直している

## 課題
入金済みの請求書の金額を減らす手段がないため、返金が帳簿に残らず、月次の売上と税額を手で直している。手での計算は端数がずれ、返金額の累計が請求額と合わなくなる。

## 解決
入金済みの請求書の明細を数量で指定して返金する操作を `billing.refunds` モジュールに用意し、帳簿の保存・監査ログ・顧客の残高・月次集計・督促・複製を返金と整合させる。

## 要件
- `billing.refunds.issue_refund(book, invoice_id, quantities, reason, actor, on)` は、`quantities` (`line_id` → 返金する数量) で指定された返金を記録し、返金 1 件を表す `Refund` を返す。`on` は返金日 (`datetime.date`)。`Refund` は属性 `refund_id`・`invoice_id`・`quantities`・`net`・`tax`・`total`・`reason`・`actor`・`issued_on` を持つ。`net`・`tax`・`total` は `Decimal` で、`total` は `net` と `tax` の和。`issued_on` は `on`
- `billing.refunds.refunds_for(book, invoice_id)` はその請求書の `Refund` を古い順に返す。`billing.refunds.refundable_quantity(book, invoice_id, line_id)` はその明細のまだ返金していない数量を返す
- 返金の純額は、値引きを按分したあとの明細の純額を基準にする。明細の累計返金純額は「明細の純額 × 累計返金数量 ÷ 請求数量」を通貨の最小単位に四捨五入した額とし、1 回の返金の純額は今回までの累計から前回までの累計を引いた額とする = 分割しても端数がたまらない
- 返金の税額は税率ごとに計算する。税率ごとの累計返金税額は「その税率の明細の累計返金純額の合計 × 税率」に請求書の税額と同じ端数処理をした額とし、1 回の返金のその税率の税額は今回までの累計から前回までの累計を引いた額とする = どう分割しても全数量を返金した時点で累計は請求額に一致する
- 返金できるのは状態が `paid` か `partially_refunded` の請求書だけ。それ以外は `InvalidTransition` を送出する
- `quantities` の検査: 数量 0 の行は無視する。すべての行が無視されて何も残らないとき、数量が整数でないとき、負のとき、まだ返金していない数量を超えるときは `ValidationError` を送出する。存在しない請求書と存在しない明細は `NotFound` を送出する
- 例外を送出した呼び出しは何も残さない = 返金の記録・請求書の状態・監査イベント・返金番号のどれも変わらない
- 返金は呼び出し元が渡した `quantities` を変更しない。請求書の明細と請求額も変更しない
- 返金番号は `RF-0001` の形式で帳簿全体の連番とする。帳簿を保存して読み直したあとも続きから振る = 同じ番号を 2 度使わない
- 返金後の請求書の状態は、全明細の全数量を返金し終えたら `refunded`、それ以外は `partially_refunded` とする
- 返金ごとに監査イベント `refund.issued` を残す。`data` は `refund_id`、`amount` (`total` を既存の `payment.recorded` の `amount` と同じ表現にしたもの)、`reason` を持つ。状態が変わる返金は、そのあとに既存の `invoice.status_changed` を残す。状態が変わらない返金では `invoice.status_changed` を残さない
- 帳簿を保存して読み直しても、返金の記録・請求書の状態・監査イベントは同じで、読み直した帳簿で続きの返金ができる
- `receivables.customer_summary` の通貨ごとの行に `refunded` (その通貨の返金の `total` の合計。返金がなければ 0) を足す。`billed`・`paid`・`outstanding`・`invoice_count` は返金の前後で変わらない
- `reports.monthly_revenue` は返金の `net` を返金日の月から差し引く。`reports.tax_report` は返金の税額を税率ごとに返金日の月から差し引く。請求書そのものは返金のあとも発行月の集計に計上されたままとする (返金日が発行月と同じなら、その月の集計は返金の分だけ減る)
- 集計は返金の直後から返金を反映する = 返金の前に同じ集計を呼んでいても古い値を返さない
- 返金された請求書は `receivables.overdue_invoices` に出ない
- `invoices.duplicate_invoice` で作る複製は、元の請求書の返金を引き継がない = 複製には返金がなく、全数量を返金できる状態から始まる。複製のあとに元の請求書へ返金しても複製には影響しない

## 非機能要件
- 標準ライブラリのみを使う
- Python 3.9 で動く

## 見た目の正本
- キャンバス: 該当なし

## 受け入れ基準 (テストケース表)
表の請求書はいずれも顧客 `C1`、発行日 `2026-03-10`、支払期日 `2026-03-31` で全額入金済み (状態 `paid`) とする。返金日は断りがなければ `2026-04-15`。`A:{L1:1}` は請求書 A の `L1` を数量 1 返金することを表す。

- 請求書 A (JPY、値引き 100): `L1` 単価 1000 × 3 税率 10%、`L2` 単価 500 × 2 税率 8% — 請求額 4270 (純額 `L1` 2925・`L2` 975、税額 10% 292・8% 78)
- 請求書 B (JPY、値引き 25): `L1` 単価 25 × 2 税率 10% — 請求額 27
- 請求書 C (JPY、値引きなし): `L1` 単価 15 × 1 税率 10%、`L2` 単価 15 × 1 税率 10% — 請求額 33
- 請求書 D (USD、値引き 0.49): `L1` 単価 10.25 × 2 税率 10% — 請求額 22.01
- 請求書 E (JPY、値引きなし): `L1` 単価 1000 × 3 税率 10%、`L2` 単価 500 × 2 税率 8% — 請求額 4380

| ID | seam | ケース | 期待結果 |
|---|---|---|---|
| AC-1 | `issue_refund` | `A:{L1:1}` (値引きあり) | `net` 975、`tax` 97、`total` 1072、`refund_id` `RF-0001` |
| AC-2 | `issue_refund` | `A:{L1:1}` を 3 回 (分割) | `tax` は 97・98・97、`total` は 1072・1073・1072 |
| AC-3 | `issue_refund` | `A:{L1:3, L2:2}` (1 回で全数量) と、`A:{L1:1, L2:1}`・`A:{L1:2}`・`A:{L2:1}` (3 回に分けて全数量) | どちらも `net`・`tax`・`total` の累計は 3900・370・4270 (請求額と一致) |
| AC-4 | `issue_refund` | `A:{L2:1}` を 2 回 (8%) | `net` は 488・487、`tax` は 39・39、`total` は 527・526 |
| AC-5 | `issue_refund` | `B:{L1:1}` を 2 回 (ちょうど半分の端数) | `net` は 13・12、`tax` は 1・1、`total` は 14・13 |
| AC-6 | `issue_refund` | `C:{L1:1}` のあと `C:{L2:1}` (同じ税率の別明細) | `tax` は 1・2、`total` は 16・17 |
| AC-7 | `issue_refund` | `D:{L1:1}` を 2 回 (USD) | `net` は 10.01・10.00、`tax` は 1.00・1.00、`total` は 11.01・11.00 |
| AC-8 | `refunds_for`, `refundable_quantity` | `E:{L1:1}` のあと | `refunds_for` は 1 件、`L1` の返金可能数量 2、`L2` は 2。属性 `invoice_id`・`quantities`・`reason`・`actor`・`issued_on` は渡した内容のとおり |
| AC-9 | `issue_refund` | 発行済みで未入金の請求書 | `InvalidTransition` |
| AC-10 | `issue_refund` | `E` を全数量返金したあとの `E:{L1:1}` | `InvalidTransition` |
| AC-11 | `issue_refund` | `E:{L1:4}` (請求数量を超える) | `ValidationError` |
| AC-12 | `issue_refund` | `E:{L1:2}` のあとの `E:{L1:2}` (累計で超える) | `ValidationError` |
| AC-13 | `issue_refund` | `E:{L1:1.5}` (整数でない) | `ValidationError` |
| AC-14 | `issue_refund` | `E:{L1:-1}` (負) | `ValidationError` |
| AC-15 | `issue_refund` | `E:{}` と `E:{L1:0}` (何も残らない) | `ValidationError` |
| AC-16 | `issue_refund` | `E:{L9:1}` (存在しない明細)、存在しない請求書 | どちらも `NotFound` |
| AC-17 | `issue_refund` | `E:{L1:1, L2:0}` (数量 0 の行) | `L1` だけ返金され `quantities` は `{L1:1}`。渡した dict は `{L1:1, L2:0}` のまま |
| AC-18 | `issue_refund` | `E:{L1:1, L2:99}` (2 行目が不正) のあと `E:{L1:1}` | 1 回目は `ValidationError` で、返金の記録・状態・監査イベントは変わらない。2 回目の番号は `RF-0001` |
| AC-19 | `issue_refund` | `E:{L1:2}` のあとの請求書 | 明細の数量と請求額 4380 は変わらない |
| AC-20 | 状態, 監査 | `E:{L1:1}` | 状態 `partially_refunded`。`invoice.status_changed` の `data` は `paid` → `partially_refunded` |
| AC-21 | 状態, 監査 | `E:{L1:1}` を 2 回 | 2 回目で状態は変わらず `invoice.status_changed` は増えない。`refund.issued` は 2 件 |
| AC-22 | 状態, 監査 | `E:{L1:1}` のあと `E:{L1:2, L2:2}` | 状態 `refunded`。最後の `invoice.status_changed` の `data` は `partially_refunded` → `refunded` |
| AC-23 | 状態, 監査 | `E:{L1:3, L2:2}` (1 回で全数量) | 状態 `refunded`。`invoice.status_changed` の `data` は `paid` → `refunded` |
| AC-24 | 監査 | `E:{L1:1}` と `D:{L1:1}`、actor `alice`、reason `返品` | 順に `refund.issued`、`invoice.status_changed`。`refund.issued` の `actor` は `alice`、`at` は `2026-04-15`、`data` の `refund_id` は返金番号、`reason` は `返品`、`amount` は E が `"1100"`、D が `"11.01"` |
| AC-25 | `store.save`, `store.load` | `E:{L1:1}` のあと保存して読み直す | `refunds_for` の全属性、状態、返金可能数量、監査イベントが同じ |
| AC-26 | `store.save`, `store.load` | `E:{L1:1}` のあと保存して読み直し、`E:{L1:1}` | 番号は `RF-0002` |
| AC-27 | `store.save`, `store.load` | `A:{L1:1}` のあと保存して読み直し、`A:{L1:1}` | 2 回目の `tax` は 98 (AC-2 の 2 回目と同じ)。読み直したあとの `tax_report` も読み直す前と同じ |
| AC-28 | `store.load` | 変更前のコードが保存した `E` のファイル | 読み込めて `refunds_for` は空、`E:{L1:1}` の番号は `RF-0001` |
| AC-29 | `customer_summary` | `E:{L1:1}` のあと (返金の前に呼んでいても同じ) | `refunded` 1100、`billed` 4380、`paid` 4380、`outstanding` 0、`invoice_count` 1 |
| AC-30 | `customer_summary` | 返金のない顧客 | `refunded` 0 |
| AC-31 | `monthly_revenue` | `E:{L1:1}` のあと (返金の前に呼んでいても同じ) | 3 月は `JPY` 4000 のまま、4 月は `JPY` -1000 |
| AC-32 | `tax_report` | `E:{L1:1}` のあと (返金の前に呼んでいても同じ) | 3 月は 10% 300・8% 80 のまま、4 月は 10% -100 |
| AC-33 | `overdue_invoices` | 基準日 `2026-04-20`、`E:{L1:1}` のあとと、別の帳簿で `E:{L1:3, L2:2}` のあと | どちらも `E` は出ない |
| AC-34 | `duplicate_invoice` | `E:{L1:1}` のあとに複製 / 複製のあとに元へ返金 | 複製の `refunds_for` は空で返金可能数量は `L1` 3・`L2` 2。発行して全額入金すると `{L1:3, L2:2}` の `total` は 4380 |
| AC-35 | `monthly_revenue`, `tax_report` | 返金日 `2026-03-20` の `E:{L1:1}` (発行月と同じ月、返金の前に呼んでいても同じ) | 3 月は `JPY` 3000、税額は 10% 200・8% 80 |

テストしないと決めたもの:
- 文字列や `None` の数量 — 呼び出し側が数値を渡す契約であり、型の検査はしない
- `2.0` のような整数値の小数 — 整数でないものの代表は AC-13 で足り、扱いを決めない
- 数量 0 を指定した存在しない明細 — 無視と `NotFound` のどちらでもよく、扱いを決めない
- 複数の不正が同時にある入力でどの例外を先に送出するか (AC-10 の全数量返金済みの請求書は状態の不正として扱う) — 呼び出し側が例外の種類で分岐する場面がなく、順序を決めない
- 返金日が発行日より前の場合と、`reason` が空文字列の場合 — 呼び出し側の責任であり、検査しない

実機確認に委ねる基準 (UI・見た目など TDD 対象外で挙動ゲートに委ねるもの):
- なし

## スコープ外
- 決済サービスとの連携など、実際にお金を戻す処理
- 一部入金の請求書への返金と、金額を直接指定する返金
- `receivables.customer_statement` と `reports.taxable_base_report` への返金の反映

## 用語
- なし (用語集 docs/crystallize/CONTEXT.md の語を使う)

## 改訂履歴
| 日付 | 項目 | 変更 | 理由 | 発見した場面 (認識合わせ / 実装 / 挙動ゲート / リリース後) |
|---|---|---|---|---|
