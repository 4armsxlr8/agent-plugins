---
name: plan-commit
description: 「planコミット」「planを消してコミット」で発動。docs/crystallize/plans/<slug>.md に基づく実装を確定させるとき。
user-invocable: true
argument-hint: "[docs/crystallize/plans/<slug>.md のパス]"
metadata:
  purpose: produce
  trigger: user
  shape: atomic
---

# plan-commit — plan をコミットメッセージにして削除する

plan ファイル (`docs/crystallize/plans/<slug>.md`) の内容をそのままコミットメッセージ本文にしてコミットし、plan ファイルと作業フォルダ (`docs/crystallize/plans/<slug>/`) を削除する。plan ファイル自体は削除されるが、コミット履歴に内容が保存される設計である。

本スキルの `<slug>` は **plan ファイルの basename** (拡張子を除いたもの) を指す。分割 plan なら `<slug>-<n>-<部分名>` が丸ごと basename になり、削除対象のディレクトリも `.commit-msg-<basename>.txt` もその名前で作る。spec の slug とは一致しないことがある。

## Input / Output

- **Input**: `$ARGUMENTS` = plan ファイルのパス。省略時は `docs/crystallize/plans/` 直下の `.md` が 1 つならそれを使い、複数あれば AskUserQuestion で選んでもらう
- **Output**: 1 コミット (メッセージ = 要約行 + plan 本文 + あれば `## Spec revisions`)。plan ファイルと `docs/crystallize/plans/<slug>/` は削除済み (spec は残る)。最終報告は `git log -1 --stat` の要点

## 手順

1. **前提確認**: plan を Read し、`git status` で未コミットの変更があることを確認する (変更ゼロなら「コミットするものがない」と報告して終了)。plan と明らかに無関係な変更が差分に混ざっているときは、処理を中断してユーザーに確認する。plan 先頭の `spec:` 行が指す spec (`docs/crystallize/specs/<slug>.md`) の変更は無関係ではない — 実装中の仕様改訂で書き換わるのが正常なので、これを理由に中断しない
2. **plan と実装の突き合わせ (簡易確認)**: plan の計画項目のうち明らかに未実施のものがあれば、一覧でユーザーに伝えて続行可否を確認する。差分の詳細なレビューは行わない (diff-review や /code-review で実施する)。実装計画がリファクタリングと機能変更の両方を含む場合は、そのまま 1 コミットにせず references/commit-granularity.md の基準に従って分割コミットする (plan 本文は最後のコミットに含める。「リファクタリングと機能変更を混在させない」原則をコミット時に確認するため)
3. **メッセージ作成**: 1 行目 = Conventional Commits 形式の要約 (plan のゴール 1 文から作る。例 `feat(auth): サブドメインURLの共通基盤に移行`)、空行、以降 = plan 本文をそのまま。**plan 本文の後に、spec の改訂履歴のうち今回追加された行を `## Spec revisions` として転記する** — spec ファイル自体は残るので履歴を追えばよいが、コミットメッセージだけを読む人にも「この実装で仕様のどこが変わったか」が分かるようにする。取得方法は spec が追跡済みなら `git diff HEAD -- <spec のパス>` を実行し、**`## 改訂履歴` 見出し以降の差分ブロックに限って** `+|` で始まる行 (表のヘッダと区切り行は除く) を抽出する — spec には受け入れ基準の表もあり、見出しで絞らないと改訂で書き換えた基準の行まで混ざるためである。未追跡 (今回新規作成された spec) なら改訂履歴の表の全行を転記する。plan に `spec:` 行が無い旧形式ならこの節ごと省く。メッセージはプロジェクト内の固定パス `docs/crystallize/plans/.commit-msg-<basename>.txt` に書く (`mktemp` は `/var/folders` 配下に書こうとしてサンドボックスに書き込み拒否されることがあるため使わない)。**書き出したメッセージファイルが空ならコミットせず中断し、その旨をユーザーに報告する** (空メッセージでのコミット作成を防ぐため)
4. **plan の削除**: 対象の plan ファイルと `docs/crystallize/plans/<slug>/` を削除する。plan が git 追跡済みなら削除も同じコミットに含める (未追跡ならファイル削除のみで消える)。**`docs/crystallize/specs/` 配下は削除しない** — spec は改訂を重ねて継続管理する追跡ファイルであり、一時的な plan とは管理方針が異なる。変更があればそのまま同じコミットに入る。**用語集 (`docs/crystallize/CONTEXT.md`、またはリポジトリ直下の `CONTEXT.md`) も削除しない** — spec と同様に残す文書であり、変更は同じコミットに入る
5. **コミット**:

   ```bash
   git add -A
   git reset -- docs/crystallize/plans/     # 未追跡の兄弟 plan・作業ファイル・メッセージファイルを外す
   git add -u -- docs/crystallize/plans/    # 追跡済み plan の削除だけを戻す
   git commit -F docs/crystallize/plans/.commit-msg-<basename>.txt --cleanup=whitespace
   rm docs/crystallize/plans/.commit-msg-<basename>.txt
   ```

   メッセージファイル自体はコミットに含めない (`git reset` でステージングを解除してからコミットし、成功後に削除する) — 含めると plan 削除と矛盾する余計な追跡ファイルが履歴に残るためである。`plans/` を一度 reset してから `-u` で戻すのは、他の分割 plan (`<slug>-<n>-<部分名>.md` とその作業ディレクトリ) が未追跡のままコミットに含まれるのを防ぐためである — 誤って含めると、次の plan のコミットで削除される不要な追加が履歴に残る。過去のコミット操作によって他の分割 plan が追跡済みになっている場合は `-u` がその変更も対象にしてしまうため、そのときだけ個別に `git reset -- <対象の分割 plan のパス>` を実行する。`plans/` に対象が何も無いと reset が pathspec の警告を出すが、終了ステータスは 0 であり問題はない
6. **確認**: `git log -1 --stat` で「plan 本文がメッセージに入ったか」「plan ファイルが削除されたか」を確認して報告する。push は行わない (リモート環境への操作はユーザーの指示があるときだけ行う)

## Gotchas

- **`--cleanup=whitespace` を指定しないと Markdown の見出しが消える** — plan は Markdown なので `#` 見出しを含む。git の既定 cleanup は `#` 行をコメントとして削除するため、見出し行がすべて除去されたメッセージでコミットされてしまう
- 1 plan = 1 コミットが基本形。差分を意味単位で分けたいときは、先に references/commit-granularity.md の基準に従って分割コミットし、最後のコミットにだけ plan 本文を入れる
- pre-commit hook がファイルを書き換えたら、その変更を add してコミットし直す (hook による修正のたびにユーザーへ確認を求めず対処する)
- `docs/crystallize/plans/` 配下に別タスクの plan が残っていることがあるため、指定された slug 以外のファイルは削除しない
