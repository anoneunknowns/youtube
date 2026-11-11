Num-Num Numbers — Fibonacci Numbers / 前工程v001

脚本・全項・数式・英語台本・背景案・画像モックアップを作成。
F₀=0〜F₄₀=102,334,155、41項（初期値2項＋加算39回）。ユーザー指定のシャム猫。
第一案は「雲の上の風の郵便局」。代案2案は文案。音声と完成動画は未生成・未実測。

入口
  concept-and-scenario.txt : 数式の生成サイクル、画面構成、数学上の注意点。
  script-and-sound-cues.txt : 全104発話の英語、日本語訳、画面キュー、仮編集枠。
  count-lines.json : 全41項の真値、入力a/b、出力c、F添字、通算、式、数詞、表示モード。
  narration.json : 発話ID、英語と和訳、表示キュー、仮時刻。手書き台本文案の正本。
  timing-plan.json : 速度仮定、語数、待機、概算尺、未実測項目。
  background-concepts.txt : 第一案と代案2案、過去8作品との比較。
  mockups/ : 1920×1080の画像、一覧、数式の受渡しプレビュー。
  qa/mockup-verification.json/.txt : 原寸の配置・字形・静止状態等の測定記録。
  qa/content-verification.json/.txt : 数列、英語数詞、式と発話ID、仮時刻の独立検算。
  character-selection.json : 当初の抽選と、その後のユーザー指定によるシャム猫への変更履歴。

素材
  背景: assets/library/worlds/cloud-post-office/backgrounds/v001/cloud-post-office-background.png
  通常姿: assets/library/characters/siamese-cat/sources/v005/neutral.png
  新規4ポーズ登録: assets/library/characters/siamese-cat/motions/fibonacci-v001/registration.json
  追加ポーズはwatch_left / present_half / present_full / delighted。共通身体基準560px。
  本画面は表示身体高400px、足支点(1655,990)。通常姿は既存1070px基準で同じ身体高へ合わせる。
  元シート・生成プロンプト・入力と参照条件・ハッシュも各素材のディレクトリへ保存。

画面とタイミング
  OLDER / NEWER / NEWの横三列の数値窓。下に大きい結果と最大2行の英語読み。
  式の数値はF₂〜F₂₀で88px、F₂₁〜F₄₀で47px固定の9桁対応モードへ一度切替。
  数式発話は『a plus b equals』まで。結果cは次のN発話で一度だけ読む。
  通常2秒は結果cの読み終わり→次の式の読み始めで、数詞だけの間隔ではない。
  mockups/formula-relay-preview.gifは12秒・音声なしの概念プレビュー。
  GIFは本番の発話時間・音声同期・完成動画の連続品質を保証するものではない。
概算: 1221語、固定遷移107.04秒、130〜150語/分で9.92〜11.18分。
  仮編集枠は150語/分から算出。採用音声のPCM実測から本番時刻を作り直す。

再現・確認（リポジトリのルートから）
  .venv/bin/python tools/render_fibonacci_mockups.py
  .venv/bin/python tools/prepare_fibonacci_design.py --check

  renderは本企画のモックアップとその配置QAを再出力する。既存完成動画や採用素材は変更しない。
  prepareの既定動作と--checkは読み取りのみ。現在の台本文案と説明文を入力として数列・時刻・台本を再計算し比較する。
  別版へ7資料を出す場合は、未存在の出力先を明示する。
  .venv/bin/python tools/prepare_fibonacci_design.py --out-dir design/fibonacci-counting-review-new
  既存資料への上書きオプションはない。既存QAも上書きしない。
  新しい検算記録を保存する場合は、未使用のQA保存先を指定する。
  .venv/bin/python tools/prepare_fibonacci_design.py --check --qa-dir design/fibonacci-counting-v1/qa/new-content-review

数学の確認
  全41項は漸化式と独立の二項係数和で一致。
  初期値と二つの1、F₃₉<1億<F₄₀、39式と全IDの一意性を確認。
  OEIS A000045 https://oeis.org/A000045 の公式検索結果と照合（2026-11-11）。本体直取得は403。
  静止画や無音GIFの確認と、完成品の音声・動画QAを区別する。過去作品の台帳と完成記録は変更しない。
