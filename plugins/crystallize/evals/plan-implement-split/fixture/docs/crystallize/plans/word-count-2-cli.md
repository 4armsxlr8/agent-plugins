# テキストの語数を数える関数と、ファイルの語数を表示するコマンドを用意する — cli

spec: docs/crystallize/specs/word-count.md
covers: AC-4, AC-5
depends-on: docs/crystallize/plans/word-count-1-core.md

## 守るべき既存挙動
- `wordcount.count_words` の挙動は変えない (1 枚目で実装したものを呼ぶだけにする)
- 新しい依存は追加しない

## 実装計画 (変わりやすい順)
1. `wordcount/cli.py` を新規作成し、ファイルを読んで `count_words` の結果を表示する `main` を実装する — AC-4, AC-5 / TDD 対象

## 検証コマンド
python3 -m unittest discover -s tests
lint: なし
E2E 評価の対象面: CLI (`python3 -m wordcount.cli <ファイル>`)。前提状態: 語数を数えるテキストファイルを 1 つ用意する

## Deviations 規約
計画から逸れる必要が出たら保守的な選択を採り、この plan の `## Deviations` に理由ごと追記して続行する。確定した要件と矛盾する逸脱 (エージェント発) は止めてユーザーに戻す。ユーザー発の仕様変更は spec の改訂として扱う (plan-implement 挙動ゲートの仕様改訂レーン)。
