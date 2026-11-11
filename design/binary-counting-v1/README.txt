Num-Num Numbers：二進数カウント動画の制作前資料

企画案
  夕暮れの庭で、赤い帽子のくまが二進数を英語で数える。
  0から1111111₂（十進数0〜127、計128個）までを仮の範囲とする。
  10はone zero、11はone one、100はone zero zeroと左から1桁ずつ読む。
  0はzeroに統一する。通常カウントでは十進数のtwoやtenへ読み替えない。
  原稿は全128個、発話770語（one 448回、zero 322回）を検査済み。

画面と構成
  主表示は7桁の位置を固定した数字カード。未使用の上位桁は空欄にし、声に出さない。
  1は暖かく点灯、0は消灯色。色だけに頼らず0/1の数字でも区別する。
  位の値64/32/16/8/4/2/1と小さいDECIMAL値を添え、点灯数＝値と誤解させない。
  読む方向は左→右、桁上がりを確認する方向は右→左。途中の誤った値は主表示へ出さない。
  導入32秒、7の後と63の後に各3秒、31の後に8秒の伸び、終幕15秒を仮置きする。
  8状態ごとの16か所に演出を設定。新しい桁の短い音6回＋終幕音1回。冒頭雑音・BGMなし。
  現時点の見積は8分35.32秒。既存oneの実測値と未生成zeroの仮値を使った計算であり、完成尺ではない。
  範囲と尺は音声の実測後に確定する。無理な早口化やtime stretchで見積へ合わせない。

見る順序
  research-reading.txt：英語での読み方と一次教材のURL、根拠と編集上の選択。
  concept-and-scenario.txt：狙い、背景テーマ、情報階層、演出、時間構成。
  script-and-sound-cues.txt：導入から終幕までの英語台詞、声・SE・動作の仮の発話窓。
  count-lines.tsv：全128個の二進表示、英語原稿、空欄を含む7桁の対応表。
  count-lines.json：全128個の機械可読原稿。display_binaryとspoken_tokensを分ける。
  episode-plan.json / cue-sheet.json / estimated-timeline.json：制作前の構成データ。
  asset-reuse-audit.txt：再利用する正本、ポーズ、音声、フォント、既存実装の制約。

画像
  assets/library/references/binary-counting/v001/key-visual.png：通常カウント101101₂＝十進45。
  同folderのstoryboard.png：導入、0、桁上がり、休憩、通常、7桁の終幕の6場面。
  01-intro.png / 02-zero.png / 03-carry.png / 04-stretch.png / 06-finale.png：各場面の原寸。
  背景原本：assets/library/worlds/binary-lantern-garden/backgrounds/v001/。
  generation-record.jsonにimage_genの最終promptと参照元を保管する。
  くまは既存の正本PNGを直接使用し、数字と文字はコードで描画した静止画モックアップ。
  mockup/index.htmlが配置の正本、mockup/storyboard.htmlが6場面の組版。
  tools/render_binary_mockups.mjsで画像を再出力できる（未使用の出力先を指定）。

制作段階
  完了：読み方の調査、128個の原稿と計算、台本・演出、背景、静止画7枚の画像レベル確認。
  未実施：新規zero/台詞/SEの生成と実測、二進数対応の動画renderer、実際のモーション検収、動画出力。
  既存の10進カウント用planner/ASRをそのまま二進数対応済みと扱わない。
  0開始、桁列のtoken照合、全128状態と770発話の同期を専用に検査してから実制作へ進む。
  第1動画・採用音声・元の2プロジェクトは変更していない。新資料は独立したpreproduction setとして登録する。
