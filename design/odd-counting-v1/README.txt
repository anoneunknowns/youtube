Num-Num Numbers 第七弾 Odd Numbers

現行の設計・制作は8分以上版v002。
  CURRENT.txt、production-run-v002.json、production-review-v002.txtを参照。
  動画・実測timeline・master・字幕・チャプター・投稿資料はoutput/odd-counting-001-v002/。
  1〜299の全150値・163発話、1080p30fps。完成MP4は8分55.80秒・16074フレーム。
  ショート動画以外は原則1本8分以上とする。
  通常2秒と読み速度を維持し、尺は区切りのよい終点まで範囲を広げて確保する。Shorts・明示例外のみ別扱い。

企画
  レッサーパンダと1〜299の奇数150個を英語で数える。
  背景は新規Mountain Cable Station。切符の組分けで一つ余ること、99から101への+2を示す。
  主数値・読み・7整数の数直線、別レイヤーの説明図。BGMと効果音なし。

資料
  character-selection.json：登録済み11体から一度の無作為抽選。
  concept-and-scenario-v002.txt：8分以上版の脚本・シナリオと背景3案。
  script-and-sound-cues-v002.txt：英語台本、日本語訳、編集枠と画面指定。I07/F02だけ299へ更新し、他11英語台詞とI/T/F編集枠はv001と同一。
  concept-and-scenario.txt、script-and-sound-cues.txt：v001の原本。既存timelineのhash参照を維持する。
  参照画像はassets/library/references/odd-counting/v002/。静止画の先行確認と完成品のqa/odd-final-qa.jsonを区別する。
  v001の採用音声・個別検査根拠はv002から参照し、変更しない。

制作条件
  導入36秒、9と101の後に各8秒追加、締め14秒。
  通常147境界は2.00秒、確認2境界は10.00秒。
  表示先行0.12秒、299後0.28秒保持。
  全尺は数詞150発話の実測合計S+364.40秒。新しい採用音声を使う場合は時刻を再計算する。
  レッサーパンダは登録済み原画の自然高と支点を使い、尾を切らず固定420px高で配置する。

完成品と検査
  output/odd-counting-001-v002/paspla-studio-odd-numbers-1-to-299-1080p.mp4
  output/odd-counting-001-v002/upload-details.txt：タイトル・概要・5チャプター。
  output/odd-counting-001-v002/english-captions.srt：英語字幕163件。
  production-qa/v002/verification.txt：全16074フレーム・150値・163発話の最終検査PASS。
  sourceと最終AACの新規ASR・CTC、語頭語尾、左右音声・無音、独立確認も完了。回帰テスト204件PASS。
  検査は自動解析と抽出画像の確認を含み、人が全編を連続試聴・視聴したという記録ではない。

画像
  assets/library/references/odd-counting/v002/storyboard.png：9場面のモックアップ。
  assets/library/worlds/mountain-cable-station/backgrounds/v001/mountain-cable-station-background.png：新規背景。
  同フォルダのgeneration-prompt.txtとgeneration-record.json：生成指示と来歴。

追加再チェック
  production-qa/v002-recheck-20261111/verification.txt：ユーザー依頼による新しい再検査PASS。
  完成MP4の150値・1350欄を独立照合し、全16074フレーム、切替等228フレーム、全163発話の新規ASR・音素・波形を確認した。
  修正を要する不備は見つからず、動画・音源は変更していない。解析差分と個別判断は同フォルダの各reportに保持する。
