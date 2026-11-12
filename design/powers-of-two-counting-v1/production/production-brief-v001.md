# 制作ブリーフ：Powers of 2 完成版 v001

共通正本：[制作](../../../docs/PRODUCTION.md)／[画像管理](../../../docs/IMAGE-ASSET-MANAGEMENT.md)／[配置](../../../docs/LAYOUT-ALIGNMENT.md)／[セットアップ](../../../docs/SETUP.md)。先行設計の`../production-brief.md`と当時のmanifestを保全し、この版へ結果を追記する。

## 識別・担当・現在地

- 作品ID：powers-of-two-counting-001-v001。制作セット：powers-of-two-counting-production-v001。2026-11-12 JST。
- 状態：完成MP4を独立検査で合格。根拠は`../production-run-v001.json`と`../production-review-v001.txt`。
- 主担当Codexが画像生成・合成・原寸レビュー・共通登録を直列実施。音声担当が原音/PCM/AAC、描画担当が本編、独立担当が数式/実画素/音声/字幕を検査。
- 設計`design/powers-of-two-counting-v1/`、出力`output/powers-of-two-counting-001-v001/`。他担当の素材/旧媒体を変更しない。

## 題材・台本・出力

- 乳幼児〜小学生が、同量コピーから値が生まれる因果を楽しむ。数式の難しさを理由に省略しない。
- `a_n=2^n`、n0..64、65項・64倍増、値1〜18,446,744,073,709,551,616。JSONの値は文字列、Python任意精度整数で検算。
- 全真値`../sequence.json`、数学QA`../qa/math-verification.json`。実測全78キュー台本`scenario-v001.txt`、実際の表示/演技との差も記載。
- 声af_heart、Kokoro/fp32、速度0.98、US short scale、andなし。最終75新規＋3既採用の完全発話。
- PCM発話合計430.923542秒＋編集134.2秒＝565.123542秒。映像565.133333秒、16,954frame、1920×1080、16:9、30fps、H.264/yuv420p、AAC48kHz stereo、BT.709/tv。
- 通常56境界は2.00秒。説明8境界は台詞の実測を加算し、速度や通常の待ちで尺を稼がない。最終尺は8分以上を実測確認。

## 背景・素材・構図・演技

- 紙と影の倍々劇場。えんじ幕・象牙紙面・木床・蝶番。既存背景と重複せず、文字/鳥を背景へ焼き込まない。
- 実物紙片→ラベル付き二群→全幅大数、指数の寄り、前景の導入/終幕を使う。背景の色替え/単純な左右反転に頼らない。
- ヤイロチョウの通常姿v001、身体参照637px、足支点(593,969)を維持。新規専用batchは`powers-of-two-production-20261112-01a1cd56`。
- 10rawのうち8寄与。5翼/1閉眼は通常姿の固定身体へ局所合成し、静かな休息2姿は共通488px参照で接地。未採用rawの細胴差や既存expanded/thinkの監査を解決済みに書き換えない。
- 共通尺度は姿勢群ごと、場面の身体高/足支点は`visual-plan/character-motion.json`。導入/寄り320px、通常230/180/150px、終幕300px。個別bboxへのfitは行わない。
- 元生成シート、入力の役割/SHA、prompt、セル矩形、派生maskと共通校正を保管。背景1672×941→1080pの約1.1483倍は、完成原寸画像で精細さを判断した。
- クマ/素数/Fibonacciの実MP4抜粋と原寸像を比較。接近/戻り、休息、二重像/跳ねを`qa-v001/actor-final-v003/root-review.json`に記録。
- 文字は実字形グループの水平/垂直center、鳥は解剖上の足支点、移動紙片は軌跡と意図した扉遮蔽を検査。出力各軸1px以内、空/切れなし。

## 音声・実装と再開

- 原音`…/speech/measurements-selected-v006.json`と`speech-acceptance.json`。新規ASR/CTC、215群の補助確認、語頭/語尾/波形と個別判断を保存。
- 元PCM/実測timelineは`audio-build/`。N029だけのcodec補正PCM/採用AAC/現行timelineは`audio-build/codec-v002/`。一定−3.5dBを原音SHAへ束縛し、他77窓と窓外はbyte同一。
- builder`tools/build_powers_of_two_episode.py`、初回描画`tools/render_powers_of_two_video.py`、AAC交換`tools/remux_powers_of_two_audio.py`、末尾修正`tools/render_powers_of_two_video_v003.py`。
- 最終検査`tools/verify_powers_of_two_video.py`、音声/フェード補助は制作記録のfiles参照。全CLIと依存/版の注意は`../README-production.md`。
- 採用音声から再制作する経路ではTTS再生成不要。原画/フォント/登録/時刻/マスター/AACと原本SHAを照合し、新しいリポジトリ内出力を使う。

## 検査・納品・保存

- [x] 数学・全値・台本・実測尺・出力条件。
- [x] 新規素材の来歴、最大表示、共通縮尺、通常姿の同一性、必要な演技。
- [x] 本編・字幕78件・章10件・タイトル/概要。
- [x] 完成MP4全16,954frame、半解像度144,327字形、原寸4,801frame/38,052字形/108,100桁。
- [x] 紙344場面、非fade actor16,901frame、5種の負対照、各軸1px以内。
- [x] 完成AACの新規左右156ASR/156CTC、個別警告未解決0、全78窓と79無音、−16.84LUFS/−1.96dBTP。
- [x] 初0.6秒/末1.2秒フェード58原寸サンプル、最終完全CREAM、2種の負対照。
- [x] 独立最終QAは同一SHA `987c324f…fc395f`へ束縛。自動検査/原寸抜粋と、人による全編視聴を区別。

納品・再現用入力は`../production-run-v001.json`へSHAで束ね、共通登録とその全体検査は`adoption-closeout-v001.json`へ別記する。素材予約は所有者が完了後に解放する。過去の媒体、候補、失敗試作と検査器の校正前記録は保全する。

Gitコミット/push/別PC再生はこの制作作業では未実施。共通台帳・再現用許可リストの保存と、共有先への反映は区別する。再生成できる巨大な復号PCM等は採用原本と分け、削除はしていない。

未解決の完成品blockerはない。次に修正する場合も、新しい版で媒体・入力・QAを保存し、現行版と当時の記録を上書きしない。
