素数動画向けのカンガルー動作素材

入口: registration.json。採用原画は expressions-sheet-v002.png、gestures-sheet-v002.png、postures-sheet.png の3シートです。frames/ は元シートの完全なセルをRGBAのまま無損失で切り出したものです。

従来の通常姿 sources/v002/neutral.png、motions/v001 の6姿勢は変更していません。ここにある通常姿は新しい動作用の描画です。元の通常姿を同一性の参照として生成しました。

描画には各frameの reference_height_px と anchor_px を使います。シート間は耳を除く頭幅で校正し、各シート内は共通の等方縮尺を保ちます。しゃがみ・空中姿勢の個別fitは禁止です。空中姿勢の足支点は解剖上の足位置であり、地面ではありません。跳躍の上下移動は動画側で加えます。

まばたき・開口笑顔には registration.json の face_overlays を使います。生成済みの目・口の部分だけを通常姿へ配置し、身体・尾を動かさず、通常姿の外形を増やさないようにします。描画用合成は元PNGの変更とは区別します。

generation/edit の各promptとrecordに正確な指示文、入力の役割・SHA-256、元生成先、出力SHA-256を保存しています。motion-sheet.png は低解像度と動作差不足で不採用です。expressions-sheet-v002-candidate.png は半透明の背景汚れ、gestures-sheet-v002-candidate.png は余分な腕があるため不採用です。候補を採用素材として読み込まないでください。

素材検査と実際の動作検査は別です。検査記録は design/prime-counting-v1/production-qa/v002-animation/、実際の音声・数値・映像検査は新版の制作記録から参照します。生成ツールは built-in image_gen.imagegen です。
