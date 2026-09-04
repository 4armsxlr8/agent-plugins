# 出典

SKILL.md の各補正値がどの出典から来ているかの対応表。SKILL.md 本文の `[出典 xxx]` は下の短縮名を指す。

| 短縮名 | 出典 | 採ったもの |
|---|---|---|
| slide | 原佑一「美しいUIを作るために デザイナーが意識している ちょっとした考え方」(CyberAgent / Ameba, Speaker Deck, 全29枚) https://speakerdeck.com/yuichi_hara7/mei-siiuiwozuo-rutameni-dezainagayi-shi-siteiru-tiyotutositakao-efang | 上方距離過大の錯視の実例 (Ameba ブログ20周年サイトの中央ロゴ: 上余白 295px / 下余白 317px)。色の面積効果の実例 (「本日開催」バッジ塗り `#298737` / 日時テキスト `#237B31`)。三角形分割錯視の実例 (再生ボタン: 左右 193px / 193px で数値中央だが左に寄って見える。三角形にボールを敷き詰めて「左側の方が重い」)。密度と重心 (Ameba ブランドサイト: 写真より本文の方が重心が外に出るので本文側のマージンを変える)。「10」の 0 のオーバーシュート例。趣旨は「数字ではなく重心でデザインしている。少しのズレは意図なので揃えないでほしい」 |
| Goodpatch | Goodpatch Blog「UIにも必要な錯視への考慮、デザイナーが行う視覚調整」 https://goodpatch.com/blog/visual-adjustiment | 上方距離過大の錯視 (文言を中央より少し上寄りに)、三角形分割錯覚 (三角形の重心が中央にくるよう配置)、色の面積効果 (目視でどちらかの明度を変える)、ハーマングリッド (余白を細く / グリッドを不規則に / 余白の列幅を広く / 背景に色付け)。数値目安はなし |
| traP | 東京工業大学デジタル創作同好会 traP「タイポグラフィーと錯視調整の話」 https://trap.jp/post/1396/ | 上方距離過大の錯視 (X・Z・H・8 は上側を小さく設計)、交点が太く見える錯視 (交点で線を細く — 書体設計向けで UI 部品には通常掛けない)、三角形分割錯覚 (数学的中心と視覚的中心の差)。数値目安はなし |
| chot | chot Inc. デザイナーユニット「Webデザインで意識したい3つの錯視効果」 https://note.com/chot_designer/n/n3128ae2086a7 | 上方距離過大の錯視の補正量「たった 1px 程度」(ボタン内テキスト、Netflix のログイン画面が例)。色の面積効果 (アイコンとテキストで色を分けて管理、特にグレー)。三角形分割錯視 (YouTube ロゴ、スライダー・プルダウンの矢印) |
| Bjango | Marc Edwards「Formulas for optical adjustments」 https://bjango.com/articles/opticaladjustments/ | 円は四角の 112.84% に拡大すると視覚的な重さ (面積) が揃う (= √(4/π))。穴や凹みのある図形は凸包の面積で重さを見積もる。正三角形は重心を円の中心に合わせる。ピクセル境界へのスナップ |
| Material | Material Design (v1) System icons — Keyline shapes https://m1.material.io/style/icons.html | 24dp グリッドの keyline: 四角 18×18dp / 円 直径 20dp / 縦長 16×20dp / 横長 20×16dp。「これらの基本形をガイドにするとアイコン間の視覚的比率が一定に保てる」 |
| prototypr | Balraj Chana「11 Optical Illusions Found in Visual Design」 https://blog.prototypr.io/11-optical-illusions-found-in-visual-design-295e7ae211b9 | スライド p.25 の活用事例 (「10」のオーバーシュート) の出典。本文はアクセス制限で取得できておらず、SKILL.md にはスライド経由の内容だけを採っている |

## 出典に数値がない項目の扱い

SKILL.md で **[経験則]** と付けた値 (オーバーシュート 1〜3%、密度差のマージン +4〜8%、細線アイコン +5〜10%) は、上の出典のいずれにも具体値がない。方向 (どちらへ動かすか) は出典どおりで、量はスキル作成時に置いた初期値。実測して更新してよい。更新したら根拠区分も書き換える。

## 正三角形の重心 (w/6 の導出)

右向きの正三角形 (幅 w = 底辺から頂点までの高さ) の重心は底辺から w/3 の位置にある。バウンディングボックスの中央は底辺から w/2。差は w/2 − w/3 = w/6。重心を容器の中心に合わせるには、三角形を頂点側へ w/6 動かす。
