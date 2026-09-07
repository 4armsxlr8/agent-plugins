---
name: plan-implement
description: 「実装開始」「planを実装」で発動。docs/crystallize/plans/配下のplanパスを渡されたときにも発動する。
---

# plan-implement

## Codex 実行境界

最初に `../../references/codex-runtime.md` を全文読む。コード変更は履歴なしの独立サブエージェントへ委任し、親は差分と検証結果を自分で確認する。変更系の子を並列起動せず、同じ checkout を使う処理は直列に進める。

要件は固定するものではなく育てるもの。UI は触って初めて分かることが残り、リリース後に利用者の声で変わることもある。忠実性とは『黙って逸れないこと』であって『変えないこと』ではない。

`plan-create` スキルが作った plan (`docs/crystallize/plans/<slug>.md`) と、その plan が指す spec (`docs/crystallize/specs/<slug>.md`) を受け取り、実装 → 検証 → コミットまでを一続きで駆動する統括役。3つのゲート（機械・挙動・例外）を順に通し、**挙動ゲートが収束するまで diff-review を作らない**。コードは書かず、実装はすべてサブエージェントに委任する。

## Input / Output

- **Input**: 起動メッセージに含まれる `docs/crystallize/plans/<slug>.md` のパス。省略時は直下の plan が1つなら確認して使う。複数なら Codex の構造化質問で選び、使えないモードでは候補を最終応答に示して止める。plan が無ければ実装せず `$crystallize-codex:spec` → `$crystallize-codex:plan-create` の順で先に plan を作るよう案内する。
- **Output**: `plan-commit` が作るコミット。進行中は plan 本体の `## 進行状況` と `## Deviations` だけへ記録し、補助進捗ファイルを作らない。spec は残り、仕様改訂があれば同じコミットに入る。

## 最重要禁則

1. diff-review はフェーズ4の挙動確認が収束するまで起動しない。
2. 子の完了報告だけで機械ゲートを通さない。親がテスト・lint・差分を再確認する。
3. 要件と矛盾する逸脱、plan にない大規模変更は停止してユーザーへ戻す。ユーザー発の仕様変更はフェーズ4の仕様改訂レーンで処理する。
4. 独立性が必要な処理でサブエージェントを使えない場合、同一コンテキストへ黙ってフォールバックしない。

## フェーズ1: plan / spec 受領と Deviations 契約

- **書込み前preflight**: plan や production code を書く前に、`../test-generator/SKILL.md`、`../code-generator/SKILL.md`、`../diff-review/SKILL.md`、`../plan-commit/SKILL.md` が解決できること、ならびに `CODEX_HOME`（未設定時はCodexの既定home）配下の `skills/.system/review-agent/SKILL.md` を解決できることを確認する。
- 公式SKILLは存在・読取可能な通常ファイルであることを確認し、`realpath` した絶対パスを `resolved_review_skill` として保持する。フェーズ3はこの値だけを使い、別パスを再解決しない。
- いずれかの依存、公式SKILLの解決・存在・読取・realpathに失敗したら、汎用レビュープロンプトや同一コンテキストへフォールバックせず、plan / production codeへの一切の書込み前に停止・報告する。
- plan と先頭の `spec:` 行が指す spec を読む。あわせて**用語集**（リポジトリ直下に `## 用語` か `## Language` を持つ `CONTEXT.md` があればそれ、無ければ `docs/crystallize/CONTEXT.md`。どちらも無ければ spec の用語節）も読む。守るべき既存挙動・実装計画・検証コマンド・Deviations 規約は plan から、要件・非機能要件・受け入れ基準（テストケース表）・用語は spec から取る。spec が無い旧形式の plan は plan 内の確定事項と受け入れ基準を使う。
- plan に `covers:` 行があれば、その plan が扱う受け入れ基準は列挙された AC と `実機:` 項目だけに限る。範囲外の AC はテストや挙動ゲートに載せない。`depends-on:` 行があれば先行 plan のファイルを確認し、残っていれば先行 plan を先に実装する。ファイルが無ければ関連するコミット本文に先行 plan のゴールがあるか確認し、見つからなければ停止してユーザーへ戻す。
- `## 進行状況` が無ければ実装項目と4つのゲート（機械/挙動/例外/確定）のチェックボックスを作る。既存なら最初の未完了項目から再開する。
- `## Deviations` が無ければ作る。可逆・局所的な逸脱だけを「計画項目 / 実際の選択 / 理由」の1行で記録する。

完了条件: plan と必要な spec を読み、次に着手する項目が1つに定まり、必要な下流契約が解決済み。

## フェーズ2: 実装

- 入出力で正解を固定できる挙動変更は TDD。UI・見た目・捨てるプロトタイプ・設定更新は非TDDとして扱う。
- TDD対象では spec の受け入れ基準表にある seam・境界ケース・テストしない範囲を合意済みの記録として使い、実装セッションで取り直さない。
- `test-generator` は `gpt-5.6-luna` / `max` の履歴なしの子へ `CRYSTALLIZE_CODEX_ROLE=test-generator`、同 SKILL の絶対パス、project_dir、該当スライス、spec の該当AC行、テストしない範囲、検証コマンド、用語集のパスと「識別子・表示文言は用語集の語を使い、『使わない語』を新たに導入しない」の規則だけを渡す。子の後で production 変更ゼロと RED ログを親が検算する。
- `code-generator` は別の `gpt-5.6-luna` / `max` の履歴なしの子へ `CRYSTALLIZE_CODEX_ROLE=code-generator`、同 SKILL の絶対パス、project_dir、同じスコープ、RED テスト一覧または修正指摘だけを渡す。親はテスト・golden・snapshot・fixture の変更ゼロを検算する。
- 非TDDは code-generator のみ起動する。異なる意図のスライスを同じ委任へ混ぜない。
- generator の逸脱は親が plan へ転記する。escalate が返ったら停止する。

完了条件: 全実装項目に実差分で確認済みの完了報告または解決済み escalate がある。

## フェーズ3: 機械ゲート

1. 親が影響範囲のテスト・lintを実行する。失敗は code-generator へ直列で差し戻し、12回で収束しなければ停止する。
2. 緑になったら、フェーズ1 preflightで保持した `resolved_review_skill`（realpath済み絶対パス）だけを使い、Codex公式内部Skillを唯一の正本とする `review-agent` を起動する（defect-first）。フェーズ3で公式SKILLを別パスから再解決しない。
   - 履歴なしの子を `model: "gpt-5.6-sol"`、`reasoning_effort: "high"`、`fork_turns: "none"` で起動する。reviewer への委任プロンプトに渡すデータは次だけに限定する:
     ```
     CRYSTALLIZE_CODEX_ROLE=code-review
     review_skill: <フェーズ1で保持したresolved_review_skillの絶対パス>
     plan: <plan の絶対パス>
     review_target_diff: <レビュー対象diff>
     verification: <検証コマンド・exit status・結果>
     output_contract: read-only / findings-first / actionable findings を P0-P3 順で返す。該当なしは `No findings.` とし、最後に overall assessment と material test gaps / residual risks を短く返す
     ```
   - reviewer は解決済みの公式 `SKILL.md` を全文読み、その契約（read-only、defect-first、P0-P3、`No findings.` を含む）を実行する。親の推論・ledger・未指定の背景は渡さない。
   - preflight済み公式SKILLの読取、または履歴なし子の起動に失敗したら、汎用レビュープロンプトや同一コンテキストへフォールバックせず、コードレビュー工程を未完了として停止・報告する。
3. 指摘修正は code-generator へ差し戻し、親が検証結果を更新して再検証する。変更後は同じ公式 review-agent 委任を再実行する。テスト自体の欠陥はユーザー確認後にだけ test-generator へ戻す。解消しない指摘は理由を Deviations へ記録する。
4. diff-review の昇格条件②対外境界または③依存追加に触れる場合だけ、別の `gpt-5.6-sol` / `high` の履歴なし read-only security reviewer を起動する。該当しなければ「security review対象外」と記録する。
5. 最後に別の `gpt-5.6-luna` / `max` の履歴なし変更サブエージェントへ、挙動・公開契約・テストを変えず、重複・不要な抽象化・複雑さだけを整理する品質整理タスクを渡す。変更があれば親が再検証する。
6. 最後のコード変更より後に全量のテスト・lintを親が1回実行する。

完了条件: コードレビュー必須、条件該当時のsecurity review、品質整理、最後の全量test/lintが完了し、未解決指摘はDeviationsに記録済み。

## フェーズ4: 挙動ゲート

- spec の「実機確認に委ねる基準」、「(モック確定・実機で再確認)」印の要件、受け入れ基準のいずれにも見た目やUI操作が無ければ「UI確認対象なし」と記録する。
- UI項目があれば、plan または既存資料にある起動コマンドを親が実行し、Codexのブラウザ・ファイル表示で優先項目と受け入れ基準の操作パスをユーザーへ提示する。起動コマンドが不明なら推測せず停止する。
- ユーザーが触って出した微修正は束ねて code-generator へ渡す。色・余白・文言の1〜2行だけは親が直接直してよい。挙動契約が変わる修正はフェーズ2へ戻す。
- ユーザーが「やっぱりこうしたい」と要件を変えたら仕様改訂レーンへ進む。まず「これは仕様の変更として spec に記録します: <変更点1行>」と一度宣言し、spec の要件・受け入れ基準・改訂履歴（場面は挙動ゲート）を更新する。分割 plan でACが増減したら該当 `covers:` 行も同時に更新する。影響するACだけを test-generator に戻し、code-generatorで実装して影響範囲の機械ゲートを再実行する。見た目だけの変更はテスト差し戻しを省く。
- 変更後は必要な検証をやり直し、ユーザー自身の「意図どおり」が得られるまで diff-review を起動しない。

完了条件: すべての操作パスでユーザー確認済み、またはUI確認対象なし。

## フェーズ5: 例外ゲート

- フェーズ4収束後、`gpt-5.6-sol` / `high` の履歴なしの子へ `CRYSTALLIZE_CODEX_ROLE=diff-review`、`../diff-review/SKILL.md` の絶対パス、project_dir、`plan: <絶対パス>`、比較基点を渡す。
- 親は生成HTML、昇格hunk数、全hunk検算を確認してCodex内で表示する。昇格0件なら diff-review のスキップ1行をそのまま示し、HTMLを作らない。別のレビュー手段を明示されてもレビュー自体は省略しない。
- ユーザーから明示的な go / no-go を得る。no-go は適切なフェーズへ戻す。

完了条件: ユーザーの明示的な go。この go はplan削除とコミットへの同意も兼ねる。

## フェーズ6: 確定

- 親が `../plan-commit/SKILL.md` を読み、同じコンテキストで plan の絶対パスとフェーズ5の go を入力として実行する。spec 改訂の転記は plan-commit に任せる。
- `git log -1 --stat`、plan と同名作業フォルダの削除、無関係ファイルがコミットされていないことを確認して報告する。

## Gotchas

- 下流名を書くだけでは実行にならない。必ずSKILLの絶対パスを解決し、fresh subagentまたは同一コンテキスト実行を契約どおり完了する。
- evaluator・generator・reviewerの子には親のledger、決着済み議論、推論過程を渡さない。
- 子は同じfilesystemを共有する。変更系の子を並列起動しない。
