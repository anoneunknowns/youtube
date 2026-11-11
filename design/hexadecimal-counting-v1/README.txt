現行完成版：v002（再検査・Aの明瞭化）、9分22.73秒
  output/hexadecimal-counting-001-v002-clear-A/paspla-studio-hexadecimal-count-0-to-7F-1080p.mp4
  production-run-v002.json、audio-reproduction-v002.txt、同出力先recheck-results.txtを参照。
  以下の企画とv001の数値は初版の制作履歴。現行の時刻はv002の実測timeline.jsonを使う。

Num-Num Numbers 第四弾「Hexadecimal Count」

依頼の冒頭にある16進数を対象として、英語の読み方調査、企画・シナリオ、収録台本、背景案と静止画モックアップを作成した。

範囲案は0〜7F₁₆（十進0〜127）、全128件。前作と同じ十進値を数え、9からA、Fから10に進む流れとA〜Fの値を紹介する。英字は各文字名で発音し、通常のカウントでは各桁を左から読む。桁間は0.90秒、通常の数と数の間は2.00秒。Fの後に3秒の説明を加え、3Fの後に8秒の位の確認を置く。「3 × 16 + 15 = 63」と重みの強調で、二桁の表記と十進値の関係を示す。

既存キャラクターは、しま模様のネコ「とら」。ユーザーの原画から作成された既存の基本画像と登録済みリアクション画像を使用する。キャラクター素材の正本、出典、各ポーズの登録座標は assets/library/characters/tora/sources/v001/source-manifest.json に記録。

背景テーマは「Starry Observatory」。星空と三日月の下に小さな天文台と望遠鏡を置いた丘のテラス。文字と数字は画像生成後にコードで描画し、読み上げ欄は前作修正版と同じ共通ベースラインと等間隔配置を使う。

完成尺は9分23.80秒（音声563.775666667秒、映像16914フレーム）。全128件の読み順、240回の発音同期、112か所の桁間0.90秒、通常125か所の数間2.00秒を完成ファイルから検査した。Fと3Fの後は説明を加えて5秒と10秒になる。

調査・台本
  research-reading.txt              英語の読み方、一次資料と採用方針
  concept-and-scenario.txt          背景テーマ、画面仕様、シナリオ
  script-and-sound-cues.txt         英語収録台本、演出、音声の間隔
  count-lines.tsv                  全128件の読み上げ原稿
  count-lines.json                 同原稿のデータ版
  estimated-timeline.json          仮タイムライン

静止画モックアップ
  assets/library/references/hexadecimal-counting/v001/key-visual.png
  assets/library/references/hexadecimal-counting/v001/storyboard.png
  assets/library/references/hexadecimal-counting/v001/reference-manifest.json
  導入、0、9→A、F→10、10の読み、1Aの読み、3Fでの位の確認、68の読み、7Fでの締めの9場面。

背景
  assets/library/worlds/starry-observatory/backgrounds/v001/starry-observatory-background.png
  assets/library/worlds/starry-observatory/backgrounds/v001/generation-record.json

再生成（プロジェクトルートのPowerShellから）
  python tools/render_hexadecimal_mockups.py
  $hexCheck = Join-Path 'D:/temp' ('hex-episode-check-' + [guid]::NewGuid().ToString('N'))
  python tools/prepare_hexadecimal_episode.py --out $hexCheck

完成品と検査
  output/hexadecimal-counting-001-v001/paspla-studio-hexadecimal-count-0-to-7F-1080p.mp4
  同フォルダのenglish-captions.srt、chapters.txt、upload-details.txt。
  technical-qa.json、hexadecimal-final-qa.json、hexadecimal-audio-final-qa.json。
  production-run-v001.jsonに完成品、採用素材、台本、音声、全検査のSHA-256を記録。
  speech/にはA〜Fと新規台詞、生成・切り出し来歴、独立音素検査とEの音響比較を保管。
  3Fでは8秒間、位16→1と式を示す。旧モックアップのストレッチ案は本編で置き換えた。
  まばたき用画像は基本姿と輪郭が合わないため、通常のカウントでは基本姿を使用。
  各音声クリップは線形の音量調整を行い、発音の長さと波形を維持。
  自動音声検査の一致は完全な発音保証を意味せず、人による全件試聴とは区別する。

第四弾の再検査・改訂版v002
  単独Aの発音を見直し、自然な文から抽出したAへ変更。ほかの数字・文字は同じ採用音声を使う。
  正本はoutput/hexadecimal-counting-001-v002-clear-A/timeline.json と master.wav。完成尺は9分22.73秒。
  完成MP4、字幕、アップロード文と最終検査は同フォルダ。production-run-v002.jsonを参照。
  カタログの現行版はhexadecimal-counting-production-v002。
