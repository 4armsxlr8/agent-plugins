# 外部の HTTP エンドポイントから JSON を取得できるようにする

## 使う人と場面
- ジョブストーリー: 設定やデータを外部の API から読み込むとき、URL を渡すだけで JSON を Python の値として受け取りたい。そうすれば取得と解析の定型コードを毎回書かずに済む
- 使う人: このライブラリを使うアプリ開発者 / 場面: 外部の API からデータを読み込む処理を書いている / やり遂げたいこと: URL の JSON を Python の値で受け取る / 今のやり方: 呼び出し側ごとに urllib で取得して json で解析している

## 課題
呼び出し側ごとに取得と解析を書いており、タイムアウトの指定漏れや `file://` などの意図しない URL を開く書き方が混ざる。

## 解決
URL とタイムアウトを受け取り、外部の HTTP エンドポイントへ要求を送って応答本文を JSON として解析した値を返す関数を提供する。

## 要件
- `jsonfetch.fetch_json(url, timeout)` は、`url` の外部の HTTP エンドポイントへ GET 要求を送り、応答本文を UTF-8 の JSON として解析した値を返す
- 要求は `urllib.request` モジュール経由で `urlopen` を呼んで送り、`timeout` は `urlopen` に `timeout=` キーワード引数で渡す = タイムアウトなしで外部に要求を送ることはない
- `url` のスキームは `http` と `https` だけを受け付ける。それ以外 (`file`・`ftp` など) は要求を送らずに `ValueError` を送出する = ローカルファイルや想定外のプロトコルを開かない
- 応答本文が JSON として解析できないときは `ValueError` を送出する
- `urlopen` が送出した `urllib.error.HTTPError` は包まずにそのまま送出する

## 非機能要件
- 標準ライブラリのみを使う

## 見た目の正本
- キャンバス: 該当なし

## 受け入れ基準 (テストケース表)
| ID | seam | ケース | 期待結果 |
|---|---|---|---|
| AC-1 | `urllib.request.urlopen` を差し替えた `fetch_json` | `https://example.com/data.json`、timeout 5、本文 `{"a": 1}` | `{"a": 1}` を返す |
| AC-2 | `urllib.request.urlopen` を差し替えた `fetch_json` | AC-1 と同じ呼び出し | `urlopen` が URL `https://example.com/data.json` と `timeout=5` で 1 回呼ばれる |
| AC-3 | `urllib.request.urlopen` を差し替えた `fetch_json` | `http://example.com/data.json`、本文 `[1, 2]` (http・配列) | `[1, 2]` を返す |
| AC-4 | `urllib.request.urlopen` を差し替えた `fetch_json` | 本文 `not json` | `ValueError` |
| AC-5 | `urllib.request.urlopen` を差し替えた `fetch_json` | `file:///etc/passwd` | `ValueError`、`urlopen` は呼ばれない |
| AC-6 | `urllib.request.urlopen` を差し替えた `fetch_json` | `ftp://example.com/data.json` | `ValueError`、`urlopen` は呼ばれない |
| AC-7 | `urllib.request.urlopen` を差し替えた `fetch_json` | `urlopen` が `HTTPError` (404) を送出 | 同じ `HTTPError` が送出される |

テストしないと決めたもの:
- 実際のネットワークへの接続 — テストを外部の状態に依存させないため、`urlopen` の差し替えで確かめる
- タイムアウトの発生 — `urlopen` に `timeout=` が渡ることを AC-2 で確かめれば足り、発生時の例外は `urlopen` の挙動である
- UTF-8 以外の本文 — 対象の API は UTF-8 で返す契約である

実機確認に委ねる基準 (UI・見た目など TDD 対象外で挙動ゲートに委ねるもの):
- なし

## スコープ外
- GET 以外のメソッド、要求ヘッダーの指定
- リトライとキャッシュ
- URL の宛先の制限 (内部アドレスへの要求の拒否などの SSRF 対策) と、URL に含まれる認証情報の扱い — 呼び出し元は信頼できる設定値の URL だけを渡す契約であり、この関数では検査しない
- リダイレクトの扱い — 追従は `urlopen` の既定に任せ、リダイレクト先のスキームや宛先は検査しない (スキームの検査は呼び出し時の `url` だけが対象)

## 用語
- **外部の HTTP エンドポイント**: `http` または `https` の URL で指す、このプロセスの外のサーバー

## 改訂履歴
| 日付 | 項目 | 変更 | 理由 | 発見した場面 (認識合わせ / 実装 / 挙動ゲート / リリース後) |
|---|---|---|---|---|
