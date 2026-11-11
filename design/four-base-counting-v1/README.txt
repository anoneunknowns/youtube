Num-Num Numbers 第五弾「Four Ways to Count」完成v001

完成動画
  output/four-base-counting-001-v001/paspla-studio-four-ways-to-count-0-to-127-1080p.mp4
  6分56.07秒、1080p30fps、英語音声。十進0〜127、全128状態。
  英語字幕、チャプター、英語タイトルと概要、最終検査は同じ出力フォルダ。
  production-run-v001.json、production-review-v001.txtが完成確認の正本。

画面と背景
  Seaside Lighthouseの海辺で、既存の黄色い小鳥が4基数の表示を案内する。
  上からBINARY / BASE 2、DECIMAL / BASE 10、OCTAL / BASE 8、HEXADECIMAL / BASE 16。
  音声のあるDECIMAL行にSPOKENを表示。重複する十進看板、桁の重み、範囲札、読み上げ欄は省いた。
  現行参照画像はassets/library/references/four-base-counting/v003/の8枚とstoryboard.png。
  v003は280pxの小鳥を採用。v001/v002の制作前比較資料は履歴であり、現行構図ではない。

音声と間隔
  音声は十進数を自然に読み、語内に桁読み用0.9秒を挿入しない。
  0は既存binary-v001、1〜127はkokoro-af-heart/v002の採用WAVを再利用した。
  新規10台詞、再利用の締め3台詞、導入のten、終幕音を実測時刻で配置。
  通常124境界は発話終了から次の発話開始まで2.00秒。8・16・64の後の3境界は5秒。
  実測正本は出力先timeline.jsonとmaster.wav。制作前estimated-timeline.jsonとは区別する。
  timeline.jsonのvideo_generated:false等は音声計画生成時の属性。完成判定はproduction-runと最終QAで行う。
  音声マスターは中間素材。再符号化時はaudio-reproduction.txtの+0.8dBを適用する。

小鳥の動作
  通常姿はcharacters/little-bird/sources/v002/の既存原画を縮小して使う。
  motions/v001/に通常姿と線・形を合わせた羽・ついばみ4姿勢と生成元・登録を保存。
  挨拶の短い羽ばたき、48の後のついばみ、96の後の小さなホップをそれぞれ一度だけ置く。
  動作の実測時刻は出力先bird-motions.json。姿勢ごとの縮尺調整はせず、足元と画質を確認した。

企画・台本と検査
  concept-and-scenario.txt、script-and-sound-cues.txt：シナリオ、背景案、英語台本。
  count-lines.json / .tsv：全128件の対応表と自然な十進読み。
  motion-and-style-review.txt：初回調査から完成版の採用判断まで。
  audio-reproduction.txt：採用音声とマスターの再構築。
  production-qa/v001/：小鳥のサイズ比較、動作の圧縮映像検査。
  preflight-review*.jsonは制作前の履歴。現在の完成品はproduction-run-v001.jsonを参照する。
