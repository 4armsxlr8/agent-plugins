# クール便の追加料金を送料に含める

## 使う人と場面
- ジョブストーリー: 冷蔵・冷凍の荷物を受け付けるとき、追加料金を含めた送料を出したい。そうすれば手で足し算をしなくて済む
- 使う人: このライブラリを使う受注システムの開発者

## 要件
- `shipping.cold.cold_fee(parcel)` は `Parcel.temperature` に応じたクール便料金を `int` で返す。`normal` は 0、`chilled` は重量の基本料金 (`rates.band_fee`) の 20%、`frozen` は 30%。それ以外の値は `ValueError` を送出する
- クール便料金は円未満を四捨五入する (端数がちょうど 0.5 円なら切り上げ)。`chilled` と `frozen` は最低 100 円
- 送料無料でもクール便料金はかかる。基準は無料にする前の重量の基本料金
- `fees.quote` はクール便のとき `breakdown` に `cold` を足し、税額と `total` に含める。税額の計算方法は変えない。`normal` の荷物の `breakdown` に `cold` を足さない
- 請求データの合計にもクール便料金を含める

## 非機能要件
- 標準ライブラリのみを使う
- Python 3.9 で動く

## 受け入れ基準 (テストケース表)
| ID | seam | ケース | 期待結果 |
|---|---|---|---|
| AC-1 | `cold_fee` | `normal`、1000g | 0 |
| AC-2 | `cold_fee` | `chilled`、1000g | 123 |
| AC-3 | `cold_fee` | `frozen`、1000g (184.5 円) | 185 |
| AC-4 | `cold_fee` | `chilled`、400g (82 円) | 100 |
| AC-5 | `cold_fee` | `frozen`、20000g (544.5 円) | 545 |
| AC-6 | `cold_fee` | `hot` | `ValueError` |
| AC-7 | `quote` | `chilled`、1000g、`tokyo`、商品代金 3000 | `breakdown` は base 615・remote 0・cold 123・tax 73、`total` 811 |
| AC-8 | `quote` | `frozen`、1000g、`tokyo`、商品代金 20000 | `breakdown` は base 0・remote 0・cold 185・tax 18、`total` 203 |
| AC-9 | `quote` | `normal`、1000g、`tokyo`、商品代金 3000 | `breakdown` は base 615・remote 0・tax 61 だけ、`total` 676 |

テストしないと決めたもの:
- 重量の上限超過 — 既存の `band_fee` の検査のまま

## スコープ外
- クール便の受付可否の判定
- 料金表の改定
