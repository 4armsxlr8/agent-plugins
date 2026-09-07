# Codex実行契約

Claude版crystallizeのワークフロー上の判断を変えず、実行基盤だけをCodexへ対応させる。

## 入力

CodexスキルではClaude固有の引数文字列展開を前提にしない。

- ユーザーが直接起動した場合は、スキル名と同じメッセージに書かれた依頼、パス、素材を入力として扱う。
- 親エージェントから委任された場合は、委任プロンプトの `Input` 節だけを入力として扱う。
- 入力がなく、安全な既定値もない場合だけ、ユーザーまたは親へ不足項目を返す。

## 独立サブエージェント

Claude版のfork設定は、Codexの独立サブエージェントで実現する。

1. Codexのサブエージェント機能を使い、親の会話履歴を渡さずに起動する。`spawn_agent` が利用できる環境では `fork_turns: "none"` を使う。
2. 委任プロンプトには、役割マーカー、読むべきSKILL.mdの絶対パス、入力、出力契約、触れてよいファイルだけを書く。
3. 評価者には作成側の推論・提案・ledgerを渡さない。事実確認に必要なコードベースと監査対象だけを渡す。
4. generatorには対象スライスに必要な確定事項と受け入れ基準だけを渡す。
5. 親はサブエージェントの完了報告を証拠とせず、差分、生成物、テスト結果を自分で確認する。
6. 必須の独立性を確保できない環境では、同一コンテキストで代行せず、利用できない機能と未完了の工程を報告して停止する。

役割マーカーは再委任ループを防ぐために使う。

- `CRYSTALLIZE_CODEX_ROLE=question-evaluator`
- `CRYSTALLIZE_CODEX_ROLE=plan-evaluator`
- `CRYSTALLIZE_CODEX_ROLE=test-generator`
- `CRYSTALLIZE_CODEX_ROLE=code-generator`
- `CRYSTALLIZE_CODEX_ROLE=code-review`
- `CRYSTALLIZE_CODEX_ROLE=html-report`
- `CRYSTALLIZE_CODEX_ROLE=diff-review`

対象SKILL.mdを読んだエージェントは、自分の役割マーカーがある場合だけその場で本処理を実行する。マーカーがなく、そのスキルが独立実行を必須とする場合は、マーカー付きの新しいサブエージェントを起動する。

サブエージェント起動時はグローバル既定値に依存せず、役割ごとにモデルと reasoning effort を明示する。`spawn_agent` が利用できる環境では、次の値を `model` と `reasoning_effort` に渡す。

- 実装・変更系 (`test-generator`、`code-generator`、品質整理、`html-report`): `gpt-5.6-luna` / `max`
- 評価・レビュー系 (`question-evaluator`、`plan-evaluator`、コードレビュー、security review、`diff-review`): `gpt-5.6-sol` / `high`

明示指定は `fork_turns: "none"` と組み合わせる。環境や上位指示に別の明示指定がある場合はそちらを優先する。

## コードレビュー専用契約

`plan-implement` フェーズ3のAIコードレビューは、Codex公式の内部 `review-agent` を唯一の正本とする。公式本文をプラグインへ複製せず、フェーズ1の書込み前preflightで `CODEX_HOME`（未設定時はCodexの既定home）配下の `skills/.system/review-agent/SKILL.md` を解決する。ファイルの存在と読取可否を確認したうえで `realpath` した絶対パスを `resolved_review_skill` としてフェーズ3まで保持し、委任 envelope の `review_skill` に使う。フェーズ3で別パスを再解決しない。

- `CRYSTALLIZE_CODEX_ROLE=code-review` を付け、履歴なしの独立子を `model: "gpt-5.6-sol"` / `reasoning_effort: "high"` / `fork_turns: "none"` で起動する。
- 委任プロンプトの入力データは `plan`、`review_target_diff`、`verification`、`output_contract` だけに限定する（役割マーカーと解決済み `review_skill` は実行メタデータ）。ledger、親の推論、未指定の背景、汎用レビュー指示は渡さない。
- 子は解決済みの公式 `SKILL.md` を全文読み、read-only・defect-first・P0-P3・指摘なしの厳密な `No findings.` を含む同スキルの出力契約を実行する。指摘は差分に導入された actionable finding に限り、最後に overall assessment と material test gaps / residual risks を返す。
- preflight済み公式スキルの読取、または履歴なし子の起動に失敗した場合は、汎用レビュープロンプトや同一コンテキストへフォールバックしない。コードレビュー工程を未完了として停止し、失敗理由を報告する。公式スキルの解決・存在・読取・realpathに失敗した場合は、planやproduction codeへの書込み前に停止する。

## スキル間の接続

CodexにClaudeのSkillツールと同じ直接呼び出しを仮定しない。

- 同一プラグインの別スキルを使うときは、現在のSKILL.mdから見た相対位置で対象ファイルを解決し、親エージェント自身も必要な契約を読む。
- 独立実行が必要なら、対象スキルを読むサブエージェントを上記契約で起動する。
- 独立実行が不要なら、対象スキルを現在のコンテキストで読み、その指示を続けて実行する。
- 下流処理を「ユーザーが後で実行してください」という案内へ退化させない。ただし、外部送信、コミット、削除、worktree作成などに新しい承認が必要なら、その承認境界で止める。

## Codexの同等機能

- ファイル探索は利用可能な検索・読み取り機能を使い、シェルなら `rg` / `rg --files` を優先する。
- 外部仕様は利用可能なWeb検索で公式一次資料を確認する。
- 構造化質問ツールが現在のモードで利用できれば使う。利用できなければ、必要な質問を最終応答で一問だけ尋ねる。
- HTMLやローカルファイルはCodex内のファイル・ブラウザ表示機能を優先する。OSの `open` が必要なら承認を得る。表示できなくても生成物の絶対パスを返せれば成果物は有効とする。
- ユーザーが明示的に許可していない外部送信、公開、push、デプロイは行わない。

## 親が検証するもの

サブエージェントから戻ったら、最低限次を親が確認する。

- generator: `git diff --name-only`、変更内容、禁止ファイル、テスト・lintのexit status。
- evaluator: JSON schema、対象ファイル、閾値、根拠、作成側情報を読んでいないこと。
- HTML生成: 出力ファイルの存在、外部参照なし、素材の欠落や捏造なし。
- commit: 対象差分、コミットメッセージ、planと一時ファイルの状態、`git log -1 --stat`。
