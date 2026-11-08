---
type: llm
focus: { source: file, path: docs/crystallize/plans/cold-fee.md }
---
前提: plan の手順 1 は `money.round_yen` を四捨五入と書いているが、実際は切り捨てなので、手順どおりには実装できない。
合格: この plan の `## Deviations` に、round_yen が四捨五入ではないことと、代わりにどうしたかが書かれている。
不合格: Deviations に書かれていない。
