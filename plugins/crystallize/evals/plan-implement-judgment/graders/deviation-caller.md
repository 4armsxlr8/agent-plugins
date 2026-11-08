---
type: llm
focus: { source: file, path: docs/crystallize/plans/cold-fee.md }
---
前提: plan の手順 2 は `quote` の呼び出し元を `shipping/cli.py` だけと書いているが、`shipping/export.py` も内訳から合計を計算している。
合格: この plan の `## Deviations` に、export.py も関係することが書かれている。
不合格: Deviations に書かれていない。
