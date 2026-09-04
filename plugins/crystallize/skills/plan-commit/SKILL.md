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

# plan-commit — plan をコミットメッセージにして畳む

plan ファイル (`docs/crystallize/plans/<slug>.md`) の内容をそのままコミットメッセージ本文にしてコミットし、plan ファイルと作業フォルダ (`docs/crystallize/plans/<slug>/`) を削除する。plan は「ファイルとしては消えるが、コミット履歴が恒久保存先になる」という設計。

## Input / Output

- **Input**: `$ARGUMENTS` = plan ファイルのパス。省略時は `docs/crystallize/plans/` 直下の `.md` が 1 つならそれを使い、複数あれば AskUserQuestion で選んでもらう
- **Output**: 1 コミット (メッセージ = 要約行 + plan 本文 + あれば `## Spec revisions`)。plan ファイルと `docs/crystallize/plans/<slug>/` は削除済み (spec は残る)。最終報告は `git log -1 --stat` の要点

## 手順

1. **前提確認**: plan を Read し、`git status` で未コミットの変更があることを確認する (変更ゼロなら「コミットするものがない」と報告して終了)。plan と明らかに無関係な変更が差分に混ざっているときは、止めてユーザーに確認する。plan 先頭の `spec:` 行が指す spec (`docs/crystallize/specs/<slug>.md`) の変更は無関係ではない — 実装中の仕様改訂で書き換わるのが正常なので、これを理由に止めない
2. **plan と実装の突き合わせ (軽く)**: plan の計画項目のうち明らかに未実施のものがあれば、一覧でユーザーに伝えて続行可否を確認する。差分の中身の審査はしない (それは diff-review と /code-review の仕事)。実装計画がリファクタリングと機能変更の両方を含む場合は、そのまま 1 コミットにせず references/commit-granularity.md の作法で分割コミットする (plan 本文は最後のコミットへ。「リファクタと機能を混ぜない」原則のコミット時の関所)
3. **メッセージ作成**: 1 行目 = Conventional Commits 形式の要約 (plan のゴール 1 文から作る。例 `feat(auth): サブドメインURLの共通基盤に移行`)、空行、以降 = plan 本文をそのまま。**plan 本文の後に、spec の改訂履歴のうち今回追加された行を `## Spec revisions` として転記する** — spec ファイル自体は残るので履歴を追えばよいが、コミットメッセージだけを読む人にも「この実装で仕様のどこが変わったか」が分かるようにする。取り方は spec が追跡済みなら `git diff HEAD -- <spec のパス>` を取り、**`## 改訂履歴` 見出し以降のハンクに限って** `+|` で始まる行 (表のヘッダと区切り行は除く) を拾う — spec には受け入れ基準の表もあり、見出しで絞らないと改訂で書き換えた基準の行まで混ざる。未追跡 (今回新規作成された spec) なら改訂履歴の表の全行を転記する。plan に `spec:` 行が無い旧形式ならこの節ごと省く。メッセージはプロジェクト内の固定パス `docs/crystallize/plans/.commit-msg-<slug>.txt` に書く (`mktemp` は `/var/folders` 配下に書こうとしてサンドボックスに書き込み拒否されることがあるため使わない)。**書き出したメッセージファイルが空ならコミットせず中断し、その旨をユーザーに報告する** (空メッセージでのコミット確定を防ぐガード)
4. **plan の削除**: 対象の plan ファイルと `docs/crystallize/plans/<slug>/` を削除する。plan が git 追跡済みなら削除も同じコミットに含める (未追跡なら rm だけで消える)。**`docs/crystallize/specs/` 配下は削除しない** — spec は改訂して育てる追跡ファイルで、plan と寿命が違う。変更があればそのまま同じコミットに入る
5. **コミット**:

   ```bash
   git add -A
   git reset -- docs/crystallize/plans/.commit-msg-<slug>.txt
   git commit -F docs/crystallize/plans/.commit-msg-<slug>.txt --cleanup=whitespace
   rm docs/crystallize/plans/.commit-msg-<slug>.txt
   ```

   メッセージファイル自体はコミットに含めない (`git reset` で unstage してからコミットし、成功後に削除する) — 含めると plan 削除と矛盾する余計な追跡ファイルが履歴に残る
6. **確認**: `git log -1 --stat` で「plan 本文がメッセージに入ったか」「plan ファイルが消えたか」を確かめて報告する。push はしない (対外的な操作はユーザーの指示があるときだけ)

## Gotchas

- **`--cleanup=whitespace` を忘れると plan が壊れる** — plan は Markdown なので `#` 見出しを含む。git の既定 cleanup は `#` 行をコメントとして削除するため、見出しが全部消えたメッセージでコミットされる
- 1 plan = 1 コミットが基本形。差分を意味単位で分けたいときは、先に references/commit-granularity.md の作法で分割コミットし、最後のコミットにだけ plan 本文を入れる
- pre-commit hook がファイルを書き換えたら、その変更を add してコミットし直す (hook との押し問答をユーザーに持ち帰らない)
- `docs/crystallize/plans/` 配下に別タスクの plan が残っていることがある — 指定された slug 以外は消さない
