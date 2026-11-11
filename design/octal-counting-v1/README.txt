Num-Num Numbers 第三弾「Octal Count」

完成版v002（1080p30fps、英語、10分42.97秒）
  output/octal-counting-001-v002-aligned-reading/paspla-studio-octal-count-0-to-177-aligned-1080p.mp4
  読み上げ欄の語を共通のベースラインと等間隔の位置に揃え、導入の空欄説明に枠を追加。
  同フォルダに英語字幕、チャプター、アップロード文、157₈の確認画像と完成検査を収録。
  音声マスターと実測タイムラインは output/octal-counting-001-v001/ を参照。
  production-run-v002.json に制作条件、検査結果、納品ファイルのSHA-256を記録。

前作と同じ十進 0〜127 を、八進表記 0〜177₈ で一つずつ数える企画。全128件。英語では表示された桁を左から順に読み、対応する十進値をウサギの看板に出す。桁と桁の間は0.90秒、通常の数と数の間は発音終了から次の発音開始まで2.00秒。7₈ と 77₈ で繰り上がりを説明し、37₈ でストレッチを挟む。

背景はフィンランド北部のイナリ周辺を参考にした「Aurora Garden」。淡い緑と紫のオーロラの下にマツとカバノキを描き、小川沿いに低木、苔、地衣類、丸みのある石を配する。赤いベレー帽をかぶったピンクのウサギが十進数の看板を持ち、右にクリーム色の学習パネルを置く。読み上げ中は桁と英単語を青緑、繰り上がりで新しく使う位は杏色で示す。

音声タイムラインは10分42.95秒。導入32秒、追加場面14秒、締め15秒を含む。収録した台詞は実測長で配置し、完成MP4の音声と表示を照合した。

調査・台本
  research-reading.txt            英語の読み方、根拠と採用方針
  concept-and-scenario.txt        背景テーマ、画面仕様、場面の流れ
  script-and-sound-cues.txt       英語台詞、演出、読み上げ間隔、効果音
  count-lines.tsv                 全128件の読み上げ原稿（閲覧用）
  count-lines.json                全128件の読み上げ原稿（データ用）
  estimated-timeline.json         既存音声の長さに基づく仮タイムライン

静止画モックアップ
  assets/library/references/octal-counting/v004/storyboard.png
  assets/library/references/octal-counting/v004/key-visual.png
  assets/library/references/octal-counting/v004/reference-manifest.json
  絵コンテは導入、0₈、7₈ の繰り上がり、ストレッチ、77₈ の繰り上がり、100₈、通常カウント、締めの8場面。マニフェストに各場面の1080p画像を記載。
  イナリ周辺を参考にした背景のクマ版は assets/library/references/octal-counting/v003/ に収録。
  比較用の初版「Aurora Garden」は assets/library/references/octal-counting/v002/ に収録。
  朝の小川と飛び石の「Eight-Step Garden」は assets/library/references/octal-counting/v001/ に収録。

背景素材
  assets/library/worlds/aurora-garden/backgrounds/v002/aurora-garden-background.png
  assets/library/worlds/aurora-garden/backgrounds/v002/generation-record.json

キャラクター素材
  assets/library/characters/rabbit-beret/sources/v001/rabbit-poses.png
  assets/library/characters/rabbit-beret/sources/v001/registration.json

再生成（PowerShell でプロジェクトルートから）
  $octalCheck = Join-Path 'D:/temp' ('octal-episode-check-' + [guid]::NewGuid().ToString('N'))
  python tools/prepare_octal_episode.py --out $octalCheck
  python tools/render_octal_mockups.py

比較用モックアップの再生成
  python tools/render_octal_mockups.py --theme aurora-garden-lapland-bear
  python tools/render_octal_mockups.py --theme aurora-garden-v001
  python tools/render_octal_mockups.py --theme eight-step-garden
