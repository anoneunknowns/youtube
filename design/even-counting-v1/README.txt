Num-Num Numbers 第六弾「Even Numbers」完成v002

完成品と現在の正本
  完成動画：output/even-counting-001-v002/paspla-studio-even-numbers-0-to-200-1080p.mp4
  1920×1080・30fps、全11070フレーム、6分09.00秒。英語音声、BGM・効果音なし。
  実測timeline.json、master.wav、英語字幕、チャプター、投稿資料は同じ出力フォルダ。
  production-run-v002.jsonとproduction-review-v002.txtが現行完成版の制作記録。
  完成MP4の全編decode・全101値・115発話・字幕の検査は出力先qa/even-final-qa.json。
  独立再検査はproduction-qa/v002-recheck-20261111/verification.jsonとverification.txt。
  v001で見つかった6語の語頭と図切替の文字重なりを修正し、最終AACと全フレームで再確認済み。
  制作前の脚本・シナリオ・estimated-timeline.jsonは設計時点の資料として保持する。

今回の内容
  0〜200を2ずつ数える、全101個の偶数。
  英語は従来の米国英語の自然読み。0も偶数として扱う。
  登録4体から無作為に選んだ黄色いことりを使用する。
  背景の第一候補はWooden Toy Workshop。代案は手芸室とタイル工房。

脚本と台本
  concept-and-scenario.txt：狙い、背景3案、構図、シナリオ、演出方針。
  script-and-sound-cues.txt：英語台詞、日本語の意味、台詞ID、編集枠、画面と音の指定。
  count-lines.json / count-lines.tsv：本カウント全101件の対応表。
  estimated-timeline.json：既存の数値音声の実測長と、新規台詞の編集枠を使った概算。
  prior-works-review.txt：公開4本とローカル完成済み1本の背景・演出の確認。
  character-selection.json：候補4体と無作為抽選結果。

参照画像
  現行の静止画9枚と絵コンテ：assets/library/references/even-counting/v002/
  一覧はstoryboard.png、通常画面の代表はkey-visual.png。
  各静止画は1920×1080。v001は修正前の履歴で、今回の提示版はv002。
  新規背景：assets/library/worlds/wooden-toy-workshop/backgrounds/v001/wooden-toy-workshop-background.png
  背景生成は組み込みimage_genを使用。生成指示は同じフォルダのgeneration-prompt.txtに保存。
  小鳥は既存原画を再利用し、積み木・囲み・文字は描画ツールで別レイヤーにする。
  画像のSHAと配置情報はreference-manifest.json、最終の静止画確認はpreproduction-review.jsonを参照。
  再作成はpython tools/render_even_mockups.py --out assets/library/references/even-counting/新しい版を指定する。
  estimated-timeline.json：既存数値音声の実測長を使った想定タイムライン。

制作前の構成計画
  導入36秒で二個一組、6個三組、0も偶数を説明する。
  本カウントは0、2、4……200。20と100の後に各8秒の確認を追加する。
  締め14秒。200を保持し、最後の2秒でフェードする。
  通常98境界は発話終了から次の発話開始まで2秒、確認2境界は10秒。
  確認は対象の発話終了0.40秒後から8秒間。次の値は9.88秒後、次の声は10秒後。
  数字の101発話の実測合計102.939125秒に266.40秒を足し、想定全尺は369.339125秒（約6分9.34秒）。
  未収録の新規台詞が導入・確認・締めの編集枠に収まることを前提とする。

画像と演出
  第一候補の工房で、導入・通常・組分け・末尾の規則・最大幅・終点を確認する。
  主数値と対応する自然な英語の読みを表示し、下段に前・現在・次の偶数カードを置く。
  0の前の負数や200の次の202は出さない。6・20の組分けと100の確認は、カードの上の独立した説明枠に表示する。
  二個の積み木を一組にする短い動きと、20個を十組にする図を使う。
  過去の庭の成長、虹、飛行物、ストレッチ、鳥の羽ばたき・ついばみ・ホップは繰り返さない。
  小鳥はsources/v002の通常姿を基準にし、ポーズの追加を成立条件にしない。

現在の段階
  新規11台詞と既存3台詞に加え、46・56・60・66・68・76の修正音声6語を実測・検査・採用した。
  静止画モックアップに加え、組分けの動作・確認場面・終幕を含む完成MP4と検査記録を保存した。
  再出力はpython tools/portable_production.pyのpreview/render/verifyで--production evenを指定する。
