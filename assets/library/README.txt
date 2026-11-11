Paspla Studio 共通素材ライブラリ

現在の動画制作にはcatalogs/library-v1.jsonのactive_production_set_idsを使う。
青空の庭で1〜300を数える動画の採用テーマはbright-garden-v002。
制作手順は直下のPIPELINE.txt、完成品と字幕はoutput/counting-garden-001-bright-v002/。

保管先
  characters/bear-beret/：キャラクター正本、元アトラス、登録座標、手振りと座る・伸びる姿勢。
  render-sources/counting-garden/：背景、小鳥、雲、虹、飛行機、葉、小物、フォントと利用条件。
  worlds/bright-garden/components/：空欄の数字板、花と蕾の独立素材。
  references/counting-garden/v002/：現行の構図と絵コンテ。動画のくまは参照図から切り出さない。
  audio/sfx/garden/v001/：オリジナル効果音10本、生成条件、権利記録。
  audio/speech/kokoro-af-heart/v002/：採用音声311本、実測manifest、生成元、利用条件、検査結果。
  branding/paspla-studio/v001/：別用途のバナー、アイコン、サムネイルの現行一式。

音声の再利用
  measurements.jsonのpathはmanifest基準の相対パス。各WAVのSHA-256と実測長を記録する。
  数は300本、セリフは11種類。再生成せず採用ライブラリを参照して使う。
  speech-acceptance.jsonがaccepted:trueで、音声・manifest・根拠のhashが一致することを必須とする。
  ミックスも--speech-acceptanceを要求し、検査後にデータが変わっていれば停止する。
  単独語認識、独立音素認識、終端の有声音スクリーニング、疑義ごとの音響比較を記録する。
  文脈中で数字が認識できたことだけで単独音声の発音警告を消さない。
  自動検査の一致は完全な発音保証ではない。人が全件を試聴したという記録にしない。
  新規生成・編集音声は未検査候補としてD:/tempへ置き、切り出し後も単独で再検査する。
  生成文、voice、model、速度、切り出し範囲、fade/pad、sourcehashを残す。

画像とモーション
  背景・キャラ・小物・文字を独立して扱い、数字や題名を共通背景へ焼き込まない。
  登録済みの矩形・足元支点・自然高を使い、ポーズごとに拡大率を変えない。
  採用モーションと制約はcatalogs/motions-v1.jsonのproduction_implementationを参照する。
  素材のv001は現行採用版を意味する場合がある。最新動画の依存素材は保持する。

管理
  最新の採用素材だけをカタログに登録し、旧出力と不採用候補は残さない。
  新版は検査と参照更新を終えてから切り替え、一時フォルダを正式な参照先にしない。
  原画、生成プロンプト、登録座標、出典、必要なライセンスは再編集・再利用のため保持する。
  関連するfour-operations／four-operations-2／four-operations-commonの輪郭統一は、ユーザーが別途明示した範囲で行う。動画の素材はプロジェクト内に版を付けて保存する。
  この記録は素材の公開再配布ライセンスを新たに付与するものではない。

二進数カウントの制作前素材
  worlds/binary-lantern-garden/backgrounds/v001/：文字とキャラを含まない、再利用用の夕暮れ背景。
  references/binary-counting/v001/：通常画面、6場面の絵コンテ、各場面原寸、hash付きmanifestと確認記録。
  企画と台本はdesign/binary-counting-v1/README.txtから参照する。
  catalogs/library-v1.jsonのpreproduction_setsに登録。第1動画のactive_production_set_idsは維持する。
  静止画の確認と、音声・モーション・完成動画の採用を区別する。

第二弾の採用素材と完成品
  audio/speech/kokoro-af-heart/binary-v001/：zero、one、15種類の台詞、音声検査・採用記録とライセンス。
  audio/sfx/binary/v001/：新しい位の短い音と、再利用した終幕音。
  背景はworlds/binary-lantern-garden/backgrounds/v001/、くまは第一弾と同じ正本と登録済み動作。
  catalogs/library-v1.jsonのbinary-counting-production-v001へ登録する。
  第一弾と第二弾をそれぞれ現行の完成品として保持する。
  完成動画と検査記録はoutput/binary-counting-001-v001/。

第二弾の看板導入版v002（保管）
  元の採用音声17クリップを使い、間隔だけを広げている。音程・声の速度は変えていない。
  看板はtools/render_binary_video_v002.pyによるコード描画。クマの正本PNGは変更しない。
  カタログはbinary-decimal-sign-v002とbinary-counting-production-v002を参照する。
  現行完成品・字幕・最終検査はoutput/binary-counting-001-v002/。

第二弾の語間0.9秒版v004（保管）
  採用済みの音声を使い、同じ二進数の中の全642語間を0.9秒へ広げた。
  中央揃えと看板はtools/render_binary_video_v003.pyを変更せず再利用する。
  現行完成品と最終検査はoutput/binary-counting-001-v004-gap900ms/。
  カタログはbinary-counting-production-v004を参照する。

第二弾の現行版v005
  桁間0.9秒を維持し、1つの数の読み終わりから次の数の読み始めまで通常2秒を空ける。
  採用済み音声・中央揃え・看板の実装は維持し、実測タイムラインと音声マスターを作り直した。
  現行完成品と全最終検査はoutput/binary-counting-001-v005-number-gap2s/。
  カタログはbinary-counting-production-v005を参照する。

第四弾の採用素材と完成品
  characters/tora/sources/v001/：既存の「とら」の正本、出典、登録座標。
  worlds/starry-observatory/backgrounds/v001/：星空の天文台の背景と生成記録。
  新規A〜Fと台詞の採用音声・検査・来歴はoutput/hexadecimal-counting-001-v001/speech/に保管。
  0〜9と再利用台詞は既存の採用ライブラリを参照し、原音の変更は行わない。
  個別音量と全体音量の調整値は同出力先audio-qa.jsonのspeech_balancingに記録。
  catalogs/library-v1.jsonのhexadecimal-counting-production-v001を現行の採用先とする。

第四弾の再検査・改訂版v002
  単独Aの発音を見直し、自然な文から抽出したAへ変更。ほかの数字・文字は同じ採用音声を使う。
  正本はoutput/hexadecimal-counting-001-v002-clear-A/timeline.json と master.wav。完成尺は9分22.73秒。
  完成MP4、字幕、アップロード文と最終検査は同フォルダ。production-run-v002.jsonを参照。
  カタログの現行版はhexadecimal-counting-production-v002。

第五弾の採用素材と完成品v001
  characters/little-bird/sources/v002/：既存の小鳥の細線原画、登録と出典。280px高で縮小表示。
  characters/little-bird/motions/v001/：通常姿に合わせた羽・ついばみ4姿勢、生成元、指示、足元登録。
  worlds/seaside-lighthouse/backgrounds/v001/：海辺の灯台背景と組み込み画像生成の指示。
  references/four-base-counting/v003/：280px構図の8枚と絵コンテ。v001/v002は比較履歴。
  音声は既存のbinary-v001のzero、kokoro-af-heart/v002の十進1〜127と締め台詞を再利用。
  新規10台詞、測定、独立認識・音素の根拠はoutput/four-base-counting-001-v001/speech/。
  動作時刻は同出力先bird-motions.json。短い挨拶、ついばみ、ホップを一度ずつ置く。
  採用カタログはfour-base-counting-production-v001。全検査後にproductionへ登録した。
  完成MP4、字幕、タイトルと概要、全最終QAは同じ出力先。
  design/four-base-counting-v1/production-run-v001.jsonが素材と完成ファイルのhashを記録する。
