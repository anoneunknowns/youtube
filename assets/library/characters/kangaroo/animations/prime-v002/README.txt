素数動画v003向けの演技改訂素材

入口は registration.json。従来の通常姿、prime-v001、汎用expanded/素材は保全し、この版を作品側から明示指定します。

過去作品と完成MP4を比較した結果、v002の手振りへの切り替えで頭・胴体が15〜17px上下する点と、長いカウント中の案内・休憩姿勢の不足が見つかりました。修正方針と比較資料は design/prime-counting-v1/production-qa/v003-comparison/ にあります。

内蔵画像生成ツール built-in image_gen.imagegen で、手振り・考える動作6コマと、展示案内3コマ・拍手3コマの計12コマを新規生成しました。元の通常姿を同一性の参照にし、prime-v001の通常姿を身体比率の参照にしています。正確な指示文は wave-think-generation-prompt.txt、presentation-clap-generation-prompt.txt、presentation-clap-transparency-edit-prompt.txt。各recordに入力の役割とハッシュ・元生成先・出力ハッシュを保存しています。

wave-think-sheet.png と presentation-clap-sheet.png が使用する生成シートです。透明PNGのalpha0内に茶・赤のRGBが残っていても、背景が実表示されることを意味しません。明色・暗色への正しいRGBA合成で確認してください。元PNGへ輪郭修正・色抜き・アルファ清掃を行っていません。

立った状態の手の動作は、登録済みの source_to_base と腕のマスクを使い、生成した腕・胸の局所差分を通常姿へ合成します。旧版のように異なる身体全体を切り替えて頭を上下させません。目・口の差分は良好な既存の生成素材を使います。合成用マスクは動画描画時のリグであり、切り出した元セルの画素変更ではありません。二重の顎や旧い手の残像がある試作は不採用です。

屈伸・踏み切り・空中・着地は良好なprime-v001の原画を継続使用します。着座途中・座位・伸び途中・伸び・立ち戻りは、採用済みのexpanded/原画を共通の身体基準高で使います。座った姿勢を個別の外接矩形で拡大しません。素材数を増やすためだけの紅茶・ダンスは追加していません。

本番は身体基準高470px、足元支点(1625,1014)を基本に全姿勢の余白を確認します。具体的な時刻は新作の kangaroo-motion.json。原寸の表情・輪郭・動作プレビューと、実際に圧縮した完成MP4の独立検査を別々に行います。最終結果は design/prime-counting-v1/production-review-v003.txt を参照してください。
