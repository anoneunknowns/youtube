Num-Num Numbers — Prime Numbers / 素数カウント
前工程 v001（ユーザー確認用）

キャラクター: カンガルー（登録済み11体から等確率で1回抽選、再抽選なし）
背景第一案: Sunlit Mosaic Museum / 日差しの入るモザイク博物館
範囲案: 2〜997、1000未満の全168素数を昇順で自然な米国英語で読む。
尺の目安: 約11〜13分。音声未生成の編集上の概算。実測尺・完成尺ではない。
本工程の成果物: 企画、脚本、全英語台本、背景原画、静止画モックアップ、数値・配置の検査記録。

確認する順序
  0. mockups/overview.jpg — 開幕・比較・カウント・終幕の4画面要約
  1. mockups/storyboard-preview.jpg — 主要11画面＋背景原画の軽量一覧
  2. mockups/key-visual.png — 通常カウント画面の原寸1920×1080
  3. concept-and-scenario.txt — 対象、学習内容、場面の順序、演出、時間計画
  4. script-and-sound-cues.txt — 英語台詞＋日本語訳＋ID＋編集枠、全168数詞
  5. background-concepts.txt — 背景3案、第一案の狙い、過去7作品との比較
  6. qa/ — 静止画・数学的内容・素材の検査範囲と結果

機械可読データ
  character-selection.json — 抽選対象と結果、採用原画の登録情報
  count-lines.json — 素数168件、順番、十進値、自然な米国英語読み、正の約数
  narration.json — 導入・カウント・説明・終幕の全188発話予定
  timing-plan.json — 通常2秒の間隔、説明用の仮枠、実測後の尺の計算法
  source-review.txt — 公開チャンネルの取得状況と実際に参照した資料

背景原画・生成条件
  assets/library/worlds/sunlit-mosaic-museum/backgrounds/v001/
  背景の生成にはbuilt-in image_gen.imagegenを使用した。
  generation-prompt.txtに正確なプロンプト、generation-record.jsonに出力SHA-256を保存。
  図のタイル・正確な文字・既存キャラクターは別レイヤーとして描画。

モックアップの再描画（リポジトリルートから）
  .venv/bin/python tools/render_prime_mockups.py
  他の環境ではPillow13.0.0と台帳指定PNG・フォントのGit LFS実体を取得し、pythonで同じコマンドを実行する。
  既存完成7作品の台帳・原画・完成動画は変更していない。

今回の前工程では音声・動画は制作していない。
静止画の個数・字形中心の確認と、完成映像の連続再生・音声検査は異なる工程である。
本番制作時は、採用音声の実測、全数値・字幕・時間の整合、連続動作、最終AACと完成MP4を検査する。
