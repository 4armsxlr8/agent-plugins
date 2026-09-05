---
name: plan-commit
description: 「planコミット」「planを消してコミット」で発動。docs/crystallize/plans/配下のplanに基づく実装を確定させるとき。
---

# plan-commit — plan をコミットメッセージにして畳む

## Codex 実行境界

最初に `../../references/codex-runtime.md` を全文読む。入力は起動メッセージまたは `plan-implement` から渡された明示的な plan パスとして扱う。コミットと plan の削除は対外操作なので、`plan-implement` フェーズ5の明示的な go がある場合だけ親から起動する。直接起動では対象一覧を表示して同意を得るまで停止する。

plan ファイル (`docs/crystallize/plans/<slug>.md`) の内容をそのままコミットメッセージ本文にしてコミットし、plan ファイルと作業フォルダ (`docs/crystallize/plans/<slug>/`) を削除する。plan は「ファイルとしては消えるが、コミット履歴が恒久保存先になる」という設計。spec は残り、仕様改訂があれば今回のコミットメッセージへ転記する。

本スキルの `<slug>` は **plan ファイルの basename** (拡張子を除いたもの) を指す。分割 plan なら `<slug>-<n>-<部分名>` が丸ごと basename になり、削除対象のディレクトリも専用一時領域の名前もその名前で作る。spec の slug とは一致しないことがある。

## Input / Output

- **Input**: ユーザーの起動メッセージまたは `plan-implement` から渡された plan ファイルのパス。省略時は `docs/crystallize/plans/` 直下の `.md` が1つならそれを使い、複数あれば Codex の構造化質問で選ぶ。使えないモードでは候補を最終応答に示して止める
- **Output**: 1コミット (メッセージ = 要約行 + plan 本文 + `spec:` 行があれば `## Spec revisions`)。plan ファイルと `docs/crystallize/plans/<basename>/` は削除済み (spec は残る)。最終報告は `git log -1 --stat` の要点

## 手順

1. **前提確認**: plan を読み、`git status --short` で未コミットの変更があることを確認する。変更ゼロなら「コミットするものがない」と報告して終了する。plan と明らかに無関係な変更が1件でも混ざっていれば停止する。plan 先頭の `spec:` 行が指す spec の変更は、実装中の仕様改訂で書き換わる正常な変更なので無関係とは扱わない。
2. **plan と実装の突き合わせ**: 明らかな未実施項目があれば一覧でユーザーに伝えて続行可否を確認する。差分の中身の審査は diff-review と独立コードレビューの仕事。リファクタリングと機能変更の両方を含む場合は `references/commit-granularity.md` に従って分割し、plan 本文は最後のコミットへ入れる。
3. **同意確認**: `plan-implement` フェーズ5の明示的な go を受けていない直接起動では、削除・コミット対象の正確な一覧を示し、明示的な同意が得られるまで進めない。
4. **対象固定**: `git status --short` と plan を突き合わせ、今回の実装ファイル、対象 plan、対象 plan 作業フォルダを明示パス一覧へ固定する。plan 先頭の `spec:` 行があれば、リポジトリルート基準で解決した spec 本体と、拡張子を除いた同名の spec 作業フォルダ (`docs/crystallize/specs/<spec-slug>/`) も対象へ含める。追跡済み spec は変更分だけ、新規 spec は本体と意図した永続作業ファイルだけを含め、別タスクの spec や plan は含めない。以降、全差分の一括stage、広域 glob、広域 reset を使わない。
5. **メッセージと復旧バックアップの作成**: 1行目を Conventional Commits 形式の要約、空行、以降を plan 本文そのままにする。`spec:` 行があり spec が変更されていれば、spec の `## 改訂履歴` 見出し以降で今回追加された行だけを `## Spec revisions` として plan 本文の後へ転記する。追跡済み spec は `git diff HEAD -- <spec のパス>` の改訂履歴ハンクから `+|` 行を拾い、今回新規の spec は改訂履歴表の行を転記する。旧形式で `spec:` 行がなければこの節は省く。メッセージは `mktemp -d` で専用一時ディレクトリを作り、その中の `commit-message.txt` をファイル編集ツールで作る。続けて手順4で固定した plan ファイル・plan 作業フォルダ・spec 本体・spec 作業フォルダを同ディレクトリの `backup/` へ構造を保ってコピーし、存在する対象を元とbyte一致することを確認する。メッセージが空、またはバックアップが不完全なら削除へ進まない。
6. **plan の削除**: 完全なバックアップの絶対パスを進行ログへ記録してから、対象 plan ファイルと対象 plan 作業フォルダだけを削除する。spec 本体と spec 作業フォルダは残し、変更があれば手順4の固定対象として同じコミットに含める。別タスクの spec と plan は削除しない。追跡済みなら削除も同じコミットに含める。
7. **明示 stage とコミット**:

   ```bash
   git add -- <手順4で固定した各パス>
   git diff --cached --name-status
   git commit -F <専用一時ディレクトリ>/commit-message.txt --cleanup=whitespace
   ```

   cached 差分に手順4の一覧外があればコミットせず停止する。コミットに失敗した場合は、手順4のパスだけを明示的にunstageし、バックアップから対象 plan ファイル・作業フォルダ・spec 本体・spec 作業フォルダを元の場所へ復元してbyte一致を確認する。復元に成功するまで一時ディレクトリを削除しない。既存パスとの衝突などで自動復元できなければバックアップを保持し、絶対パスと復旧手順を報告して停止する。コミット成功と手順8の確認が済んだ場合だけ専用一時ディレクトリを削除する。
8. **確認**: `git log -1 --stat` で plan 本文と `## Spec revisions` がメッセージに入り、plan が消え、対象 spec 本体と意図した spec 作業ファイルが同じコミットに入り、無関係ファイルが入っていないことを確認して報告する。push はしない。

## Gotchas

- **`--cleanup=whitespace` を忘れない** — plan は Markdown の `#` 見出しを含み、git の既定 cleanup では見出しがコメントとして削除される。
- 1 plan = 1コミットが基本形。意味単位で分けるときは `references/commit-granularity.md` に従い、最後のコミットだけに plan 本文を入れる。
- pre-commit hook が新しいファイル変更を生じさせたら自動追加しない。対象・テスト・差分を再検証し、手順4の一覧外なら停止して報告する。
- commit失敗を「planは消えたがメッセージ本文は一時ファイルにある」状態で終えない。plan作業フォルダには ledger・impact・モックがあり、本文だけでは復旧できない。
- `docs/crystallize/plans/` 配下の別タスクは削除も stage もしない。
