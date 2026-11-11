# ことりのリアクション線幅調整 v3

2026-11-03。通常姿勢v5と、ゲームで使う12ポーズの表示線幅を合わせるため、v2のことりatlasを編集した。旧v2の画像・catalog・verification・runtime登録は履歴として変更しない。

- 方法：built-in `image_gen` の画像編集、`transparent_background=true`。
- 編集対象：`../reactions-v2/bird-reactions.png`。
- 線の参照：`../revisions/bird-side-outline-v5.png`。
- 出力：[bird-reactions.png](bird-reactions.png)。
- alpha・各マスの余白・線幅・ハッシュ：[raster-metrics.json](raster-metrics.json)。
- 第1問の配備登録：[runtime-first-question.json](runtime-first-question.json)。くまは既存v2を参照したまま、ことりだけ通常姿勢v5と新atlasへ更新している。

## 維持した造形とポーズ

4列×3行、1448×1086、各マス362×362。順序は `blink / tap_down / tap_pop / think / aha / success_ready / success_air / success_land / oops / retry / cheer / signature` を維持した。淡い黄色の紙の質感、茶色の点目または単純な閉じ目、小さいくちばし、一本の翼線、上向きの尾、二本の足を保ち、外周と翼・足・くちばしの線を強めた。頬紅、目の白い光、模様、装飾、背景、影、新しいキャラや小物は追加していない。

画像全周のalpha最大0、各マスの境界alpha最大は0または1で、描画の可視閾値6未満。12マスすべてに全身が収まり、最も狭い余白も21pxある。alpha128以上・8px以上の連結成分は12個。近隣マスへの目に見えるはみ出しは計測で検出していない。

## 表示と接地の登録

ことりの表示自然高87.5、くまを1とした高さ0.25という既存の暫定値を保つ。新atlasのblinkはalpha6以上の頭頂63から接地318まで255pxであり、全12ポーズに等方縮尺 `87.5 / 255` を一つだけ用いる。通常姿勢v5には専用の実測値 `87.5 / 656` を使い、輪郭の変更による可視範囲の差を補う。

各ポーズは可視範囲の水平中央をanchor189へ合わせ、立つポーズの足元を接地318へ合わせる静的な位置補正だけを行う。`tap_pop` と `success_air` の元から描かれた浮き量は、それぞれ従来の表示位置約6.62px・16.04pxを保つ。輪郭の広がりに対する小さい補正であり、追加のジャンプアニメーションやポーズごとの拡大縮小は加えていない。

同じ局所的な茶色判定で、先頭の `blink` ポーズの左右各5行の水平輪郭幅を読み取った中央値は、旧atlas約2.96pxから新atlas約4.29pxへ変化した。通常姿勢v5は約3.93pxである。曲率・紙の質感・アンチエイリアスの影響がある局所測定であり、全12ポーズの輪郭全周に一律の太さがあることや、ユーザー承認を意味しない。

## 実画面レビューと採用

2026-11-03、制作担当が [通常姿勢](../../../design/completion-v1/neutral.png)、[タップ](../../../design/completion-v1/tap.png)、[正解・空中姿勢](../../../design/completion-v1/correct-air.png)、[正解・縮小表示](../../../design/completion-v1/correct-small.png) を確認して採用した。通常姿勢とリアクションの輪郭が読め、体の相対サイズ・接地・ジャンプの浮き量・単純なシルエットが保たれることを確認した。ユーザーによる新しい承認を示す記録ではない。

現在の配備ステータスとキャプチャの一覧は [runtime-first-question.json](runtime-first-question.json) を参照する。旧v2のレビュー記録は履歴のまま保持している。

## 生成プロンプト

Use case: precise-object-edit. Asset: our existing TRANSPARENT 4-column x3-row game sprite atlas, twelve poses. Image 1 bird-reactions.png is the ONLY EDIT TARGET. Image 2 bird-side-outline-v5.png is the supporting reference for the strengthened warm brown linework only; do not add another bird or replace the twelve poses with the reference pose. Preserve ALL twelve original birds in the EXACT same row-major pose order, layout, positions, padding and comparable anatomical size; preserve the baked jump lifts. Keep4columns and3rows of equal SQUARE cells, ideally the same1448x1086 canvas and362x362 cells. Every bird remains complete inside its own cell with transparent margins; never clip wing/tail/foot or bleed into another cell. Change only the warm dark-brown contour and simple wing/feet/beak linework to be clearly thicker and more uniform. Match image2's outline thickness RELATIVE TO ITS VISIBLE HEIGHT, so that when any of these poses is shown at87.5px natural height the lines read about4pixels. A standing atlas bird about251pixels high should have roughly10-12pixel brown contour, approximately1.6x the present strokes. This needs an observable increase, not merely darker color. Preserve the same pale yellow watercolor/paper fill, small orange beak, plain brown dot-eye or single closed-eye curve, one soft pointed upturned tail, two small orange feet. No eye whites/highlights/glints, blush, crest, feather detail, ornaments, shadows, glows, additional characters or props. Keep the existing expression and individual pose in every cell, including raised wings, hops, squat and head turn. Do not mirror or redesign. Preserve GENUINELY TRANSPARENT alpha outside the twelve birds; no opaque background or simulated checkerboard. Do not draw cell borders, text, numbers or labels. Output ONLY the edited atlas.
