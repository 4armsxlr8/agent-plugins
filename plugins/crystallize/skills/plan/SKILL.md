---
name: plan
description: 「plan」「実装計画」「planを作って」で発動。docs/crystallize/specs/<slug>.md のパスを渡されたときにも発動する。
user-invocable: true
argument-hint: "[docs/crystallize/specs/<slug>.md のパス]"
metadata:
  purpose: produce
  trigger: user
  shape: orchestrated
---

# plan

`spec` が確定させた要件 (`docs/crystallize/specs/<slug>.md`) を受け取り、**実装手順** を1枚 (`docs/crystallize/plans/<slug>.md`) に書き出すスキル。
plan は使い捨ての文書で、後段の `/plan-commit` がそのままコミットメッセージ本文にして削除する。要件は spec 側に残るので、plan には手順と、手順を安全にするための情報 (守るべき既存挙動・検証コマンド) だけを書く。

要件を新しく決めることは本スキルの仕事ではない。決め直しが必要になったら `spec` に戻す (手順 2)。

## Input / Output

- **Input**: `$ARGUMENTS` = `docs/crystallize/specs/<slug>.md` のパス。`spec` スキルが複数タスクを扱った場合は**複数の spec パスを渡してもよい** (spec 1 つにつき plan 1 枚を書き、並列可否の仕分けは手順 5)。省略時は `docs/crystallize/specs/` 直下で最も新しい `.md` を1行で確認する。spec が1つも無ければ plan を書かず、`/spec` で先に要件を決めるよう案内して終了する — spec のない plan は要件を実装計画の中で暗黙に決めることになり、それが決まった経緯がどこにも残らない
- **Output**: `{projroot}/docs/crystallize/plans/<slug>.md` (plan 本体)。作業ファイルは `{projroot}/docs/crystallize/plans/<slug>/` 配下 (`impact.md`)。slug は spec と揃える

## 最重要禁則

1. **プロダクトコードを書かない・編集しない**。Write してよいのは `docs/crystallize/plans/<slug>.md` と `docs/crystallize/plans/<slug>/` 配下のみ。
   理由: impact で既存コードを読み込んだ直後は「ついでに直せる」が最も湧く区間で、書き始めた瞬間に計画がそのコードを正当化する方向へ歪む (サンクコスト)。実装は plan と spec を受け取った別セッションの仕事。spec の書き換えが必要になったら自分で編集せず `spec` スキルを改訂モードで起動する (手順 2)。
2. **要件を plan で決め直さない**。決まっていない要件に気づいたら、実装計画の一項目として埋めずに `spec` へ戻す — ユーザーが見ていない要件が計画に紛れ込むと、どこで決まったかが追えなくなる。

## 手順

### 1. spec を読む

spec を Read し、ゴール・要件・受け入れ基準 (テストケース表)・スコープ外・用語を把握する。ledger や mock.html は読まない — 決着した論点の経緯は実装に不要で、読むと plan が経緯の再説明で膨らむ。

### 2. impact — 守るべき既存挙動の裏取り

開発途中プロジェクト特有の論点 (すでに動いているものとの整合性) を Explore subagent で裏取りし、`docs/crystallize/plans/<slug>/impact.md` に書く。

- 変わる既存挙動 (ユーザーから見えるもの優先)
- 移行が必要なデータ・設定
- 触ってはいけないもの (依存されている挙動・公開インターフェース)

**impact から要件レベルの新しい論点が出たら、plan を書き進めずに `spec` スキルを改訂モードで起動する** (Skill ツール、args = spec のパス)。例: 既存挙動と要件が両立しない、移行の可否をユーザーが決めていない。ここで自分で決めると、ユーザーが決めていない要件が実装計画の一項目として紛れ込む。

### 3. plan の書き出し

`docs/crystallize/plans/<slug>.md` を次の形式で書く。

```markdown
# <ゴール 1 文 (spec の先頭行と同じ)>

spec: docs/crystallize/specs/<slug>.md

## 守るべき既存挙動
impact の要点 (変わる既存挙動 / 移行が必要なデータ・設定 / 触ってはいけないもの)

## 実装計画 (変わりやすい順)
1. ユーザーが差し替えたくなる可能性が高いもの (データモデル・型・見える挙動) を先頭
2. …
N. 機械的な作業 (リファクタ・配線・テスト整備) は末尾にまとめて 1 項目
各項目に「対応する受け入れ基準の ID (AC-n)」と「TDD 対象 / 対象外」を添える

## 検証コマンド
テスト・lint のコマンドを 1 行ずつ

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
```

- **並び順が本体**: ユーザーは先頭だけ精読すればよい、という設計にする。網羅的で長い計画は読まれない
- 受け入れ基準の各行が、いずれかの実装計画項目に対応していること。対応しない行が残るなら計画に漏れがあるか、spec に実装不能な基準がある (後者なら手順 2 と同じく spec へ戻す)
- 要件・受け入れ基準そのものを plan に転記しない — 二重管理になり、spec を改訂したときに plan 側が古いまま残る。plan-implement は spec も読む

### 4. 監査 (必須)

書き出した plan は、ユーザーに提示する前に `plan-evaluator` (Skill ツール、fork 実行) に監査させる。args = plan のパス。誤前提・計画から漏れた受け入れ基準は実装後の手戻りとして跳ね返るため、ここで止める価値がある。

- 渡すのは plan のパスだけ。impact.md は渡さない — 監査が plan + spec だけで行われることが、plan の自己完結性の検査を兼ねる
- 起動時は context JSON を `docs/crystallize/plans/<slug>/eval-context.json` に書いて渡す (`project_dir` / `plan` / `output_contract.eval_file` = `docs/crystallize/plans/<slug>/eval-plan-<n>.json`)。パスだけを渡すとフォールバック経路に入り、eval JSON がプロジェクト直下の `output/` に落ちて `plan-commit` の `git add -A` で履歴に紛れ込む。`plans/<slug>/` に置けば plan-commit が plan ごと消す
- `passed: false` なら指摘箇所を裏取りからやり直して plan を修正し、再監査にかける。`rewrite` (見出し単位の置換案) が返っていればそれを基にする
- **2連続不合格で停止**: 監査が2回連続で `passed: false` になったら、3稿目を書かずに止まる。`score` と不合格の具体的理由 (`feedback_structured.high`) をユーザーに提示し、**plan の底にある前提かゴール自体が間違っていないか**を直接尋ねる。3稿目はその回答を反映してからにする (以降も同様)。同じ plan が2稿続けて落ちるのは、文面の磨き込み不足ではなく前提側の誤りのシグナルとして扱う

合格したら要点をチャットに示す (30 行を超えるなら `html-report` で HTML 化する。plan 本体は md のまま)。

### 5. 複数 spec の仕分けと配置

複数の spec から plan を作った場合、全 plan の impact を突き合わせ、触るファイル・モジュールの交差を判定する — 交差しなければ並列可、交差するなら順序を決めるか1本に統合する。進行中の他 worktree の plan があれば、それとの交差も同じ基準で確認する。仕分け後の探索で見えていなかった交差が判明したら、並列をやめて順序提案に切り替える (誤った並列はマージ衝突として跳ね返る)。

並列可と判定したら**並列配置** (どの worktree でどの plan か・交差したものはどの順序か) を小さな表で提示して合意を取る。**合意後の配置は案内で終わらせず、本スキルが自分で実行する** (案内文止まりの接続は実際には実行されない、が過去セッションで繰り返し観測された失敗の型):

1. `git worktree add` で worktree を作成する (git ネイティブ機能 — 特定ツールに依存しない)
2. `plans/<slug>.md` と `plans/<slug>/` を担当 worktree へ移動する。**spec は追跡状態で扱いを分ける** — `git ls-files --error-unmatch specs/<slug>.md` が通る (追跡済み) なら worktree 側に既に同じファイルがあるので、**移動せず、未コミットの改訂分だけをコピーする** (`mv` すると本流の作業ツリーに spec の削除が残る)。追跡されていない (今回新規に書いた) spec は `specs/<slug>.md` と `specs/<slug>/` ごと移動する — コミットされていないため worktree には現れず、移し忘れると実装セッションが plan 先頭の `spec:` 行を解決できない
3. 各 worktree でセッションを起動する — Orca が使える環境なら orca-cli で worktree を管理下に置いて Claude を起動し、`/plan-implement <plan の絶対パス>` を terminal send で送る。無い環境では、worktree ごとの雛形プロンプトを提示してユーザーに各ターミナルで開いてもらう (対話セッションが必要なため、起動だけは環境の道具に依存する)

以降の対話 (挙動ゲート・例外ゲート) は各 worktree のセッションが直接ユーザーと行う。本セッションは配置の完了報告 (worktree 一覧と各セッションの状態) で終了し、司令塔として残らない。

### 6. 案内して終了

**新しいセッションで** `/plan-implement` に plan を渡して実装を開始する旨を案内する (実装 → テスト → 動作確認 → diff の例外確認 → plan-commit までは plan-implement が一本で駆動する)。案内と一緒に、新しいセッションにそのまま貼れる最初のプロンプトをコードブロックで提示する (絶対パスで書く — 新セッションがどの cwd で開かれても迷わないため):

```
/plan-implement /path/to/docs/crystallize/plans/<slug>.md
```

---

## Gotchas

- **plan 本文から `plans/<slug>/` へ相対リンクを張らない** — plan は `/plan-commit` でコミットメッセージになり、`plans/<slug>/` はその時点で削除される。リンク先が消えた文書が履歴に残る。`specs/<slug>.md` へのリンクは可 (spec は残る)
- **プロンプトに plan の要約を膨らませない** — 実装に必要な情報が文書の外に漏れ出すと二重管理になる。足りない情報に気づいたら plan か spec 側に書き足す
