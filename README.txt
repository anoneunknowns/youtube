Paspla Studio：現在の制作一式

第五弾完成動画v002（4基数同時カウント、十進0〜200、11分02.37秒）
  output/four-base-counting-001-v002-to-200/paspla-studio-four-ways-to-count-0-to-200-1080p.mp4
  2進・10進・8進・16進を同時表示し、十進数の自然な英語読みで数える。
  海辺の灯台と280pxの既存小鳥。短い羽ばたき、ついばみ、ホップを維持。
  全201値・804表記、通常197境界2秒、確認3境界5秒。8分以上を検査済み。
  完成動画の全編decode、表示・同期・全215発話のASRと波形検査を通過。
  字幕、チャプター、英語タイトル・概要、最終QAは同出力フォルダ。
  design/four-base-counting-v1/production-run-v002.json
  design/four-base-counting-v1/CURRENT.txt
  assets/library/references/four-base-counting/v004/key-visual.png
  旧v001（0〜127・6分56秒）は変更せず履歴として保持。

第四弾完成動画v002（16進数0〜7F₁₆、十進0〜127、9分22.73秒）
  output/hexadecimal-counting-001-v002-clear-A/paspla-studio-hexadecimal-count-0-to-7F-1080p.mp4
  星空の天文台と既存キャラ「とら」。再チェックで単独Aの発音を見直し、自然な文から抽出したAに変更。
  桁間0.90秒、通常の数間2.00秒。全128件・240発音の表示、音声、同期を再検査済み。
  英語字幕、チャプター、YouTube用タイトル・概要、検査記録は同フォルダ。
  design/hexadecimal-counting-v1/production-run-v002.json
  design/hexadecimal-counting-v1/README.txt

第三弾完成動画v002（8進数0〜177₈、十進0〜127、10分42.97秒）
  output/octal-counting-001-v002-aligned-reading/paspla-studio-octal-count-0-to-177-aligned-1080p.mp4
  イナリ周辺を参考にした「Aurora Garden」で、ピンクのウサギが十進数の看板を持つ。
  1080p30fps、英語音声、桁間0.90秒、通常の数の間2.00秒。全128件の表示と音声を検査済み。
  読み上げ欄の全語を共通のベースラインと等間隔の位置に揃え、導入の空欄を示す枠を追加。
  英語字幕、チャプター、YouTube向けタイトルと概要、完成検査は同フォルダ。
  design/octal-counting-v1/production-run-v002.json
  design/octal-counting-v1/README.txt
  assets/library/references/octal-counting/v004/key-visual.png
  assets/library/references/octal-counting/v004/storyboard.png

第二弾完成動画v005（二進数0〜1111111₂、十進0〜127、21分31.10秒）
  output/binary-counting-001-v005-number-gap2s/paspla-studio-binary-count-gap900ms-numbergap2s-1080p.mp4
  第一弾と同じ声・くまを使い、導入、全128状態の桁読み、休憩、終幕を収録。
  桁間0.9秒を維持し、1つの数の読み終わりから次の読み始めまで通常2秒。
  途中の説明・ストレッチは既存の長さを維持。クマの看板に十進数を大きく表示。
  DECIMAL/Say、式と丸印、範囲札の上下中央を修正済み。完成映像の最大中心誤差0.5px。
  1080p30fps、英語音声、桁と単語の同期強調、BGMなし。
  英語字幕・チャプター・アップロード文・最終検査も同フォルダ。
  design/binary-counting-v1/production-spec-v005.txt
  design/binary-counting-v1/production-review-v005.txt
  design/binary-counting-v1/production-run-v005.json
  確認用映像・音声：同出力先のvalue-gap2s-preview.mp4 / .wav（約20秒、1110→1111を含む）。
  修正前の完成品も保持。

完成動画（英語1〜300、青空版、8分16.97秒）
  冒頭は効果音なし。BGMなし、効果音は10種類を計33回。
  output/counting-garden-001-bright-v002/paspla-studio-count-1-to-300-blue-sky-1080p.mp4

字幕・チャプター・アップロード文・最終検査
  output/counting-garden-001-bright-v002/

再利用するキャラクター、背景、効果音、採用音声
  assets/library/README.txt
  catalogs/library-v1.json

制作・再利用の実行手順
  PIPELINE.txt

現行仕様・脚本・制作確認
  design/counting-video-v1/production-spec-v2.txt
  design/counting-video-v1/sound-cue-script-v2.txt
  design/counting-video-v1/blue-sky-production-review-v002.txt

過去の完成版は履歴として保持し、現行の採用先は上記およびカタログで管理する。
現在使用する元素材やライセンス、別用途のチャンネル画像は保持している。
素材のv001はその素材の現行採用版である場合があり、旧動画を意味しない。
ユーザーのmaterials/は変更していない。関連するfour-operations／four-operations-2／four-operations-commonの輪郭統一は、別途明示された依頼の範囲で実施する。

第二弾：二進数カウントの企画・制作資料
  design/binary-counting-v1/README.txt
  英語の読み方調査、全128個の原稿、シナリオ、英語台本、SE設計、背景、静止画モックアップを保管。
  assets/library/references/binary-counting/v001/key-visual.png
  assets/library/references/binary-counting/v001/storyboard.png
  完成版は0〜1111111₂（十進0〜127）。制作時刻はoutput/binary-counting-001-v005-number-gap2s/timeline.jsonが正本。
