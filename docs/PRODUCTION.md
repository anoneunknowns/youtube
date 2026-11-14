<a name="既存作品の再出力と新作の制作"></a>

# 動画の制作・再出力仕様

> この公開版の現行作品と参照先は、同梱のカタログ・公開profileに合わせています。制作原本専用の資料は「公開版には未同梱」と明示します。全履歴用のarchive検査やdoctorには、未同梱の再現依存一覧・原本資料・ローカル動画を別途戻す必要があり、cloneだけで揃うとは扱いません。

この仕様は、設計、素材・音声の採用、本編の出力、完成MP4の検査、公開文、保存の工程を定めます。作品固有の決定と実施結果は [制作ブリーフ](../templates/production-brief.md) と各制作記録へ残します。

| 確認する内容 | 正本 |
|---|---|
| 現行の採用版・再出力の入口 | [作品台帳](../catalogs/library-v1.json)と[作品ごとの重要な条件](#作品ごとの重要な条件) |
| 画像の来歴・品質・完成原画の演技・担当予約 | [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) |
| 枠内配置・実描画の抽出・軸別許容差 | [配置仕様](LAYOUT-ALIGNMENT.md) |
| 実行環境・他PCへの移送 | [セットアップ](SETUP.md) |
| 保存対象・共有状態 | [ファイル構成](PROJECT-MAP.md)・[GitHub公開運用](GITHUB-PUBLICATION.md) |

既存作品は、採用済みの原画・音声・実測タイムラインから再出力します。新しい音声の生成や、題材・台本・演出の変更は改訂として別の入力・出力・検査記録を用意します。

新作・品質改訂は、次の順に進めます。既存入力からそのまま再出力する場合は [既存作品の再出力](#既存作品を再出力する) と [作品ごとの重要な条件](#作品ごとの重要な条件) から入り、完成品の検査・登録・保存は共通の工程へ合流します。

| 工程 | 設計・確認の入口 |
|---|---|
| 題材・台本・構図を決める | [新作の設計](#新作の設計) |
| 画像・音声を選び、不足や不備へ対処する | [画像素材の並行生成・管理](#画像素材の並行生成管理)・[音声の採用](#音声を再利用新規採用する) |
| 全動作を短片で確認し、採用入力を固定する | [本編前の圧縮動作確認](#本編前の圧縮動作確認) |
| 完成MP4と納品物を検査して採用する | [完成MP4の検査と登録](#完成mp4の検査と登録)・[公開文の書式](#公開用タイトルと概要の書式) |
| 再現依存・保存先・共有範囲を確定する | [再現用入力](#再現用入力をgitへ追加更新する)・[保存と整理](#作業を区切るときの保存と整理) |

再開時や品質改訂の判断には [制作で得た共通メモ](#制作で得た共通メモ) も使います。

## 新作の設計

開始時に [制作ブリーフのひな形](../templates/production-brief.md) を `design/<新しい企画>/production-brief.md` へコピーし、仕様リンクをコピー先に合わせます。作品固有の決定事項、担当、実装・QAの対応、根拠と再開点を記入し、共通の受入条件はひな形から参照する各仕様に従います。

企画の初めに選定したキャラクターを伝え、脚本・台本、背景コンセプト、画像モックアップを用意します。ユーザーの指定がなければ、キャラクターは登録済み素材からランダムに選定して構いません。

ショート動画以外は原則1本8分以上とします。尺を満たすために数の間隔や読み速度などの視聴感を変えず、既存の通常2秒の間隔を保ち、範囲を区切りのよい終点まで広げます。Shortsまたはユーザーが明示した例外だけを別扱いにします。偶数の6分版など過去の完成品は当時の仕様・尺の履歴として保持します。

企画時に、採用音声の実測長、通常の待機、説明・休憩の時間から完成尺を見積もり、実測後に確定します。

1. `design/<新しい企画>/` に、対象年齢、数の範囲、表示する基数、ナレーションの読み方、目標尺を明記する。
2. 脚本と英語台本を作り、導入、通常カウント、お題に必要な説明・節目、終幕を分ける。各台詞にIDと編集枠を付ける。
3. 数学上の真値を定義し、表示・図・音声・字幕を同じ状態に結び付ける。基数の異なる表記は一つの十進真値から派生させ、全値の対応表を作る。
4. 背景は数字やキャラクターを焼き込まない原画として保存し、植生、地域、季節、色をテーマに合わせる。
5. 先に選定・通知したキャラクターの通常姿、足元支点、自然高、動作の最大幅を調べる。線幅、顔、体格、縮小品質を原寸で比較する。
6. 導入、通常画面、お題に必要な説明・節目、最大桁数、終幕のモックアップを作る。最も長い数値や文字列も同じ文字サイズで収まるか確認する。
7. 音声の実測長から尺を確定し、編集枠と動作を調整してから本番を描画する。

### 数の状態と動く数式

項の値、添字、演算回数、途中計算、数える対象、進捗の確定時刻を区別します。初期値の繰返し、非単調な変化、再説明、停止条件など、題材の例外も状態表へ含めます。途中計算を新しい項として数えたり、再説明で進捗を重ねて加えたりしない設計にします。

数式や値を動かす場合は、出発元、移動中、到着先の役割を決めます。値を移す演出か複写する演出かを明記し、意図しない二重表示、元の値の残留、到着時の欠け、次の計算での復元漏れを確認します。文字サイズや添字への移行も、静止した両端だけでなく途中の字形・桁・位置を調べます。数値・図形・説明文の対応は、描画実装とは別に検算します。図のフェードは、静止した代表画像だけでなく途中フレームで文字が重ならないことも確認してください。

### お題に合わせた構図と背景

新作ごとに、数の性質・説明の順序・キャラクターの役割から画面構成を設計します。前作の「キャラクターを右または左に固定し、反対側に大きな数値カードを置く」配置を既定のテンプレートとして流用しません。左右の交代や反転だけで構図の変化とせず、お題に合う見せ方を毎回考えます。

- 台帳が指定する過去作品の実画面と比較し、新作の背景コンセプトは過去作品と重複させない。同一舞台の再利用をユーザーが指定した場合は、その指定と意図を仕様に記録する。教材の置き方、キャラクターの位置・大きさ、視点、画面の主役も検討し、背景の色やキャラクターを替えただけで比較を済ませない。
- 中央で教材を扱う、下部から案内する、教材を囲む、全景と寄りを使い分けるなど、学習内容に役立つ構図を選ぶ。これらは候補であり、順番に使い回す固定パターンにはしない。
- 導入・説明・通常カウント・節目・終幕の役割に合わせて画面を構成する。組分け、受渡し、増え方、完成までの進捗など、お題そのものから視覚的な変化を作る。同じ配置を長く使う場面も、意味に沿った変化や案内を検討する。
- 数字・読み・図の見やすさと視線の流れを優先し、構図の切替や移動は学習の流れに合わせる。長い数値、最大桁数、指さし、伸び、跳躍、遷移途中でも、意図しない教材の遮蔽・文字切れ・図形との衝突がないか確認する。教材を持つ・触れるなど意図した接触は、意味と読みやすさを保つ形で設計する。
- 絵コンテと制作仕様に、採用した構図の理由、キャラクターと教材の関係、過去作との差、場面ごとの変化を記録し、全画面のモックアップで確認する。

枠内要素は設計時に [配置仕様](LAYOUT-ALIGNMENT.md) で水平・垂直の意図を定義し、モックアップで確認します。

### 画像の精細さと表示品質

通常の横長動画は、YouTubeの[解像度とアスペクト比の公式案内](https://support.google.com/youtube/answer/6375112?hl=ja)にある16:9・1920×1080（1080p）を本プロジェクトの標準とします。縦動画・Shortsや別の解像度では、採用する出力サイズと比率を作品仕様に記録します。書き出し形式は[公式の推奨エンコード設定](https://support.google.com/youtube/answer/1722171?hl=ja)も参照します。

素材の生成・登録時の精細さ・画風の受入と検査記録は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) に従います。

### キャラクター演技と不足素材

新規制作・改修するキャラクターとイラスト小物の姿勢・表情は、[Issue #3](https://github.com/anoneunknowns/youtube/issues/3) に従い、全体を描いた完成透過PNGを1枚ずつ切り替えて再生します。原画の線・色・縦横比を保ち、不足する中間姿勢も全体を描いた原画として追加します。描画処理や取り込み先アプリで、頭・目・腕等の部品合成、変形、メッシュ、モーフ、クロスフェードや補間によって中間姿勢・表情を生成しません。瞬きや頷きにも適用します。絵全体の移動・左右反転・等比拡縮、場面の影・水しぶき・光等の演出は使用できます。教材の数値・図形の動作は、この姿勢生成の制限とは別に設計・検査します。

各コマのPNGとSHA-256、支点、基準高を既存形式の `asset.json` に登録し、`clips.json` にコマ順と各コマの保持時間を記録します。再生側は指定時刻の完成PNGを選び、そのまま保持します。作品では実際に使った登録・クリップ・PNGを固定パスとSHAで参照し、汎用素材のcurrent更新だけで採用入力を差し替えません。過去の採用媒体と検査記録は保持し、改修した動作からこの規則を適用します。

脚本の出来事に合わせて、挨拶、教材を示す動作、考える・気づく反応、節目の喜び、静かな待機・着座・伸び、終幕の仕草を選びます。通常姿や瞬きが表示されることだけで演技が十分とは判断しません。クマを含む過去作品の実MP4と、原寸・全画面・時間順の動作抜粋で比較します。長いカウントでは、最も静かな区間と仕草の繰返し方も確認します。原画枚数、動作率、静止秒数は全作品共通の目標値にしません。

- 指さし・視線・反応は、実際の教材の方向、台詞ID、計算や読了の時刻と対応させる。目立つ仕草は、数値の読みや切替を妨げない間へ置く。静かな姿勢保持は発話中にまたがってよいが、教材への注意と読みのテンポを保つ。
- 良好な素材は再利用する。不足する表情、手の開閉、関節を曲げた途中姿勢、屈伸・踏み切り・着地など、必要な箇所だけ新規に描き直した候補を用意し、組込み前に既存と比較する。改善が明確で退行がない場合だけ採用し、同等・判断不明・悪化なら既存を維持する。詳細は [画像管理仕様の採用判断](IMAGE-ASSET-MANAGEMENT.md#選択から採用への反映) に従う。
- 肩・肘・手首・手先のつながり、掌の向き、顔との前後関係は [画像管理仕様の演技の受入](IMAGE-ASSET-MANAGEMENT.md#腕手などの部品演技) に従い、全体を描いた各コマと切り替え前後で確認する。
- 瞬き・頷きは、その時の腕や身体も含めた完成原画で必要な中間姿勢と完全な周期を用意する。保持時間を配分し直した場合も、教材・発話時刻を照合する。動作窓の入口・途中・保持・戻り・直後を確認し、意図しない身体の跳ね、二重の顔や手、内部線の残像、輪郭の欠け、ちらつきを不合格とする。意図した頷き・屈伸・移動は、支点との関係を別に検査する。
- 新規原画、派生セル、再利用、バイト一致の参照コピー、別名による状態を区別する。登録状態やコピーを、新しく生成した独立原画の枚数として数えない。

形の破綻と、演技の意味が明瞭であることは別に判断します。静止画で顔や手足が成立していても、お辞儀の深まりや動きの軸が前後の姿勢とつながるかを確認します。投影による頭や帽子の見え方の変化と、別キャラクター化・個別拡大を区別します。比較範囲と方法は [画像管理仕様の動作確認](IMAGE-ASSET-MANAGEMENT.md#動作の確認範囲) に従います。

場面ごとに表示サイズ・位置を変える場合は、画面上の身体基準高、支点、移動軌跡、最大動作範囲を定義します。同じ場面・表示尺度の動作群には共通の換算を適用し、場面間の遷移も確認します。配置のために原画の登録基準を書き換えません。同じ動作の常時ループや毎作同じ仕草の追加を既定にせず、学習内容と場面に合う演技を選びます。

## 画像素材の並行生成・管理

生成・登録・採用の前に、[画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) で担当予約・来歴・用途・品質を確認します。現在の担当と在庫は [管理一覧](../assets/library/character-assets.html)、画風の指摘は [詳細監査](../assets/library/collections/character-style-audit/v001/index.html) を参照し、必要な対処を制作計画へ反映します。

## 音声を再利用・新規採用する

採用済みの `measurements.json` と `speech-acceptance.json` を優先します。本文、voice、model、速度、dtypeが異なる音声を既存採用版として扱いません。

別PCで既存ライブラリを新作へ再利用する場合は、元のゲートを変更せず、現在のcloneに対応する派生ゲートを作ります。

```powershell
python tools/portable_speech_library.py --library assets/library/audio/speech/kokoro-af-heart/v002 --out-dir output/new-local-speech-gate
```

この処理は採用WAVと検査根拠のSHA-256を検証します。履歴に残る元PCの絶対パスは派生記録で解決し、元の採用記録・原音・根拠を上書きしません。

文脈付きの生成音声から単語を取り出す場合は、`tools/extract_reviewed_word.py` で切り出し条件と元音声のSHA-256を残し、前後語の混入や語末切断を切り出した音声でも再検査します。`tools/register_speech_library.mjs` は検査候補を新しいライブラリ版へ収納するツールで、登録後も全件の検査と採用ゲートが必要です。

新しい音声を作る場合の流れは次のとおりです。

1. 未使用の候補フォルダへ生成し、生成文、声、モデル、速度、切り出し・fade・padとSHA-256を保存する。
2. 正解文や隣の数字を入力しない単独ASRで確認する。
3. 独立CTC音素、語末、波形、必要な試聴で余分な母音、子音欠落、反復、途中切断を確認する。
4. 警告ごとの判断と根拠を残し、未解決のまま採用しない。
5. 採用ゲートと実測マニフェストを作成してからミックスする。

ASRの数値一致や原音との波形一致だけでは、原音に含まれる発音上の不備を検出できません。偶数v002では、無声の摩擦音で始まる数詞の先行有声音も調べ、問題のあった6語を別テイクへ置き換えました。完成AACでも語頭・語尾と認識器の差分を確認します。

関連ツールは `generate_speech.mjs`、`generate_speech_candidates.mjs`、`verify_speech.mjs`、`verify_phonemes.mjs`、`verify_terminal_tails.py`、`review_speech_acceptance.mjs` です。個別CLIの元PC固定パスには注意し、[セットアップ](SETUP.md) と各ツールの引数を確認します。

別PCで新規候補を作る場合は、移植用の候補生成・音素検査を使います。`jobs.json` は `id` と `text` を持つ配列で用意します。出力先は未使用の候補フォルダにします。

```json
[
  {"id": "intro-new", "text": "Let's count together."}
]
```

```powershell
node tools/portable_speech_candidates.mjs --jobs jobs.json --out output/new-speech-candidates --cache $modelCache
node tools/verify_speech.mjs --manifest output/new-speech-candidates/manifest.json --cache $modelCache --ffmpeg ffmpeg --out output/new-speech-asr.json
node tools/portable_verify_phonemes.mjs --takes output/new-speech-candidates/takes.json --cache $modelCache --ffmpeg ffmpeg --out output/new-speech-phonemes.json
```

英語本文 `text` を指定した候補からは、生成ツールがASR用 `manifest.json` を同時出力します。生成来歴を含む `takes.json` と測定マニフェストは形式が異なるため、入力を取り違えないようにします。候補生成だけでは採用になりません。

数値の意味が文脈の中で認識できても、単独音声の発音警告を消す理由にはしません。自動認識の一致を、人による全件試聴や発音の完全な保証として記録しません。

### 同一信号への発音根拠の継承

同じ本文・声や高い波形相関だけで発音監査を継承しません。AACのパケット内容、PTS/DTS、継続時間、形式、先頭末尾の扱い、左右のデコードPCMを照合し、認識用の切出し条件が同じならクリップのSHAも比較します。実際のコピー元と直接比較した祖先が異なる場合は、その経路も明記します。元の発音根拠と警告の判断を検証し、今回の波形・境界検査、新規ASR/CTCの件数を別記します。同一信号の再認識を繰り返すだけで確認を増やした扱いにせず、不一致や未解決の発音には追加検査・修正を行います。

## 本編前の圧縮動作確認

静止原画、離散キーポーズ、圧縮短片、完成作品、実時間視聴・試聴は [画像管理仕様の確認範囲](IMAGE-ASSET-MANAGEMENT.md#動作の確認範囲) で区別します。離散キーのGIFや時間順の抽出画像を見たことを、滑らかな動作や全編の実時間視聴の完了へ読み替えません。

全編を描く前に、実際の背景・教材・登録尺度・支点を使った短い圧縮MP4を作ります。全動作種類と、左右・表示尺度・身体状態の異なる組合せ、開始から通常姿へ戻るまで、瞬きとの接続、最長表記と受渡しを含めます。原寸、全画面、想定する縮小視聴サイズで、演技と教材の読みやすさを確認します。短片の検査条件と記録は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md#本編前の圧縮短片) を正本とします。

問題が繰り返されるという指摘は、一つの時刻だけの修正に限定しません。同じ素材・変形・合成処理を使う動作へ確認を広げ、修正後は元の指摘区間も再確認します。

採用する短片の原画、登録、実装、タイムライン、動作設定をパス・SHA-256で固定します。本編は確認済みの入力から作り、変更があれば影響する短片を更新して再確認します。採否を記録した候補と根拠は保持し、再試行は別の保存先へ出します。短片の合格と、完成した全編MP4の最終QAは別の工程です。

## 完成MP4の検査と登録

計画時の `production_ready:false` や `video_generated:false` は、その時点の属性です。完成の判定は対象の制作記録 `production-run` と、実際の完成MP4へ結び付けた最終QAで行います。短片、原画、予定座標、正常なデコード、ハッシュ一致のどれか一つだけを、完成品の品質判断へ読み替えません。

### 技術・内容・音声・納品物

- 全編をデコードし、採用した解像度・fps（通常横長動画は1920×1080・30fps）、色タグ、フレーム数、映像・音声の終端、AAC形式、音量、true peakを確認する。
- 数の範囲・個数・順序・例外・説明式を独立に検算し、表示・図・台本・字幕・音声・時刻を照合する。題材固有の進捗や個数の演出も実画から調べ、確定時刻を確認する。
- 全数値の前後、発話直前・開始・終了・直後、桁上がりなどの境界、説明、最後の値、フェードを確認する。長い数値は行全体と各桁を照合し、更新中の異なる値の混在、空白、文字切れ、意図しない重なりを探す。
- 最終AACを採用WAVと照合し、読み間違い、語頭・語尾の切断、予定外の音、クリップ、同期を確認する。左右差はソース・符号化・時間・音量を調べて判断し、符号化後の左右波形が完全一致するという前提を置かない。
- 字幕・チャプター・タイトル・概要を、実測タイムラインと完成範囲に照合する。映像だけの改訂で納品文を保つ場合も、対象MP4との対応と各ファイルの一致を記録する。

### 画面と演技

[画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) の精細さ・演技と、[配置仕様](LAYOUT-ALIGNMENT.md) の両軸配置を、圧縮後の完成MP4で検査します。

選んだ表情・中間姿勢・仕草が実画に反映されていることを、全動作種類と設計上の各動作窓で確認します。代表例は密な時間順フレームで、各窓は前・途中・保持・戻り・直後を含めて調べ、必要な箇所を掘り下げます。長い静止区間、仕草の繰返し、過去の実MP4との差、全画面での教材の読みやすさも確認します。不足や不自然さがあれば素材生成・組込み・短片確認へ戻り、改訂した完成MP4で再検査します。

### 観測方法と対照検査

自動検査は、実画から何を測ったかを明記し、期待値・件数・章・公開文の条件を今回の入力から確認します。他作品の件数や条件をそのまま流用しません。予定した動作窓が存在することと、実際に腕が動いたこと、全身の安定、形や速度の自然さは別の判定です。

- 腕・眼・口など別の部位の変化と通常時の圧縮ノイズを分けて校正する。AA縁や小さな字形を保持する抽出条件も、[配置仕様](LAYOUT-ALIGNMENT.md) に従って確認する。領域が重なる場合は、瞬きだけで腕が動いたと誤判定するなどの混入がないか、実際の単独動作で確かめる。局所検出用マスクの合格を、全腕の形・位置の保証にしない。
- 静止画への差替え、意図的な位置ずれ・残像・ちらつきなど、検出対象に合う正例・負例を用意する。別部位だけが変わる対照も使い、動きを見つける能力と無関係な変化を拾わない能力の両方を確認する。旧不良動画を負例に使う場合も、その時刻の実状態を独立に確認し、ファイル名や過去の失敗件数だけで判定しない。
- 警告が出たら、対象MP4の実画、測定領域、期待値、ノイズ校正を照合し、媒体の不備と観測器の誤りを切り分ける。文字の近接によるROI混入は [配置仕様](LAYOUT-ALIGNMENT.md) に従う。合格に合わせて許容差を緩めたり、実際の対象を切り捨てたりしない。
- 観測器を訂正した場合は、失敗した結果・原因・旧実装を保ち、別版の実装と新しい出力先で対象MP4を再観測する。検査範囲、対象外、正例・負例、解決した警告、残る限界を記録する。

### 記録と採用先の切替

完成MP4、採用入力、実行したコード・ツール、各QA、納品物をパス・SHA-256で束ねます。比較した作品、構図・演技の判断、不足素材への対処、全編の自動解析範囲、実視認した一意フレームと動作窓を区別して残します。同じフレームを複数の検査で採取した件数と、一意の観測数も分けます。

自動解析、時間順の抽出画像・動画抜粋の確認、新規ASR・CTC、同一信号への発音根拠の継承、人による全編の実時間視聴・試聴は別の工程です。実施していない確認を完了と記録しません。音声継承は [同一信号の照合条件](#同一信号への発音根拠の継承)、画像確認の範囲は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md#動作の確認範囲) に従います。

検査と制作記録の確定後にカタログの採用先を切り替えます。既存の完成品・原画・コード・QAは当時の証拠として保全し、後から見つかった不備を過去の合格記録の書換えで消しません。媒体を変えない再検査は同じMP4のSHAへ新しいQAを結び、不要に動画の版を増やしません。アップロードが作業範囲に含まれる場合は、YouTube側のHD処理完了後の再生画質も確認します。

### 証拠の固定と再試行

入力→出力→QA→制作記録の順にし、書込み中の標準出力ログ、一時JSON、一覧自身、更新予定の受入記録を相互にハッシュ参照させません。一時検査出力は走査対象外へ置き、終了後に保存します。当時の固定スナップショットと可変の現行資料を分け、ハッシュで参照したコード・素材・登録は後から上書きしません。再試行は別版にし、元データの不備と未完了の出力を読んだ失敗を区別します。

## 公開用タイトルと概要の書式

Num-Num Numbersシリーズの標準書式です。ユーザーが示したタイトル・概要の例を基準とし、追加指定があれば優先します。題材・範囲・キャラクター・見どころは完成動画に合わせて書き換えます。

### タイトル

タイトルは英語1行で、題材、開始・終了の値、シリーズ名を次の形にまとめます。波括弧は置換用であり、投稿文には残しません。

```text
Count in {Base Name} from {start} to {end} | Num-Num Numbers
Count {Topic Name} from {start} to {end} | Num-Num Numbers
```

- 基数を数える場合は`Count in Hexadecimal`など、数列や数の種類では`Count Fibonacci Numbers`など、自然な英語で使い分ける。`Numbers`を全題材に機械的に付けない。
- `from ... to ...`は作品の始点と終点を示す。非単調な数列もあるため、最小値・最大値と取り違えない。値の表記は動画と同じ基数を使う。
- 末尾は正確に` | Num-Num Numbers`とし、縦線の前後に半角空白を置く。技術的な版番号や検査情報を付け足さない。

書き方の例：

```text
Count in Hexadecimal from 0 to 7F | Num-Num Numbers
Count Fibonacci Numbers from 0 to 102,334,155 | Num-Num Numbers
```

### 概要

概要は英語で、次の4ブロックを空行で区切ります。第3ブロックのブランド名とURLの間には空行を入れません。ファイル末尾の改行は許容します。

1. 題材と案内役を紹介する短い1文。キャラクターの名前が設定済みなら使い、未設定なら種類などで自然に紹介する。固有名を捏造しない。
2. 数の範囲、画面で見られる動きや仕組み、学習の見どころを数文で説明する1段落。必要に応じて十進値との対応や一時停止して確認する点を含める。文数や単語数を固定せず、実際にない説明・演出を約束しない。
3. 固定のブランド表記と公式URLを2行で記載する。ダッシュは`—`（em dash）、URLは末尾の`/`を含めて下記のとおりとする。
4. `━`（U+2501）を18字並べた区切り線。

```text
{One short sentence introducing the topic and character.}

{One paragraph describing the range, what viewers will see, and the learning highlights.}

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━
```

ユーザー提示の概要の例：

```text
Count in hexadecimal, or base sixteen, with Tora the striped cat.

Follow the symbols from hexadecimal 0 to 7F as the sign shows the matching decimal values from 0 to 127. Read each symbol from left to right, learn the values of A through F, and see how F becomes 10. Pause along the way to check the place values.

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━
```

この例のTora、基数、範囲、A〜Fの説明を他作品へそのまま流用しません。フィボナッチのように初期値が複数ある題材では、概要で`0 and 1`などを適切に説明します。

### 納品時の確認

- 別指定がなければ、この書式へ章一覧・ハッシュタグ・絵文字・実装情報・QA値などを自動追加しない。章一覧は別ファイルで保ち、概要へ載せるかはユーザーの指定に従う。
- タイトルと概要の始点・終点、基数、初期値、到達条件、キャラクター、紹介する演出を完成動画と照合する。
- `youtube-title.txt`、`youtube-description.txt`、両者を空行でつないだ`upload-details.txt`を用意し、内容の一致を確認する。現行公開文の保存先と対応する完成MP4のSHAを作品の記録へ明記する。
- 公開文だけの改訂と動画の改訂を区別し、以前の納品文と当時の制作・検査記録を保持する。既存作品へこの仕様を遡って適用したことにはしない。

## 再現用入力をGitへ追加・更新する

以下は制作原本の再現依存を確定する手順です。新作・新版の検査と制作記録を確定し、カタログの採用先を更新してから実行します。GitHubへ出す範囲の選別と専用公開worktreeの操作は [公開運用仕様](GITHUB-PUBLICATION.md) に従い、この処理の成功だけを公開完了と記録しません。

```powershell
python tools/update_production_archive.py --write
python tools/update_production_archive.py --check
git lfs status
git status --short
```

`--write` はカタログから必要な入力を再計算し、`reproducibility/production-inputs.json` と `.gitignore` の管理マーカー内の許可リストを更新します。`--check` はこれらの一致とファイルのSHA-256を確認し、管理ファイルを書き換えません。収納方針は `reproducibility/archive-policy.json` にあります。ローカル保持対象とGit共有対象は別です。完成MP4等の動画は現在push対象外で、必要なら別途保管・移送します。過去のMP4向けLFS属性だけを取得保証にしません。この一覧にはローカル動画を含む再現依存もあり、Git取得物だけの一覧ではありません。必要な動画を元のパス・SHA-256で戻してから `--check` と `doctor` を使います。再描画で旧SHAの一致を保証せず、旧QAや期待SHAを復元の代用に書き換えません。

共通カタログの採用切替と再現用入力の更新は管理担当が直列に行います。検査・更新が担当ロックや途中変更で停止した場合は、他担当の作業状況と差分を確認してから再実行し、ロックを自動削除しません。二つの管理ファイルはそれぞれ完全な内容へ置換しますが、一括更新ではありません。片方の置換後に停止した場合も差分を保全し、競合を解消して `--write`、`--check` で整合を確認します。

差分で採用原本、作品固有の台詞、実測timeline、master、動作情報、必要な根拠が揃っていることを確認してコミットします。全 `output/` を強制追加してキャッシュや未採用候補を混ぜないでください。Gitの行末正規化で原本のSHA-256が変わらないよう、`.gitattributes` の設定も維持します。

## 作業を区切るときの保存と整理

データの役割と保存対象は [ファイル構成の管理区分](PROJECT-MAP.md#管理対象を区別する) を正本とし、次の順序で作業します。

本仕様の媒体保全は、現在の利用・再制作・必要なQAに使うものを対象にします。容量整理は、明らかに再生成できる大容量動画や用済みの旧build・cacheを優先し、小さい素材の用途細分化のために制作・公開を長時間止めません。判断が曖昧なものは保持して更新を進めます。詳しい判断と削除記録は [削除手順](IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合) に従い、当時のパス・SHA・採用・検査記録を現在の媒体の提供状況と分けて保持します。

対象・判断・実施結果・保留事項・保存点・確認範囲は 常設の整理記録（制作原本の参考資料・公開版には未同梱: `reproducibility/organization-20261112-v001/manifest.json`） またはその新しい版へ記録します。ローカルのGit保存点は、共有先への反映や別PC検証と分けて扱います。

1. 担当と進行状況を確認する。画像は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) の予約を先に確認し、他担当の生成中領域へ入って調査・整理しない。制作中の出力やロックも、古さだけで不要と判断しない。
2. 整理候補ごとに、保存先・用途・採用版・制作記録・再現用入力・素材在庫・QAからの参照を確認する。未登録・未追跡の原本や `materials/` も区別し、判断できないものは現位置に保留する。
3. 残す原本・候補・来歴・証拠と、除ける作業データを分け、理由と対象を記録してから整理する。二重保管なら残す正本とSHA一致、参照の対応を確認する。過去QAを書き換えて参照を消したり、期待ハッシュを変更して原本の変化を隠したりしない。
4. 完成検査後の大量の描画中間PNGは、採用入力・runtime・QA証拠の必須参照が0で稼働中でないことを確認し、対象・SHA・件数・容量・再stage手順を残して削除できます。ffconcatだけを保持したencode-only履歴は、PNGを再stageするまで直接encodeできないことを記録します。原画・画像候補・過去採用媒体を古さだけで削除しません。
5. 整理後は `python tools/verify_workspace.py` と `python tools/update_production_archive.py --check` で参照・実体・再現用入力を確認し、行った変更と検査範囲を残す。媒体を変えていない整理を、新しい画風・動作・音声・完成MP4の検査として記録しない。

中断・引継ぎ時は [作品別brief](../templates/production-brief.md) 等へ、採用ID、入力・出力・QAの保存先、担当、完了した工程、未解決事項、次に行う作業を残します。保存・共有の状態は [ローカル保存と他PCへの共有](PROJECT-MAP.md#ローカル保存と他pcへの共有) の区別で記録し、実施前のコミット・共有先反映・別PC検証を完了と記しません。環境やキャッシュを除く場合も、再開に必要な固定版・取得条件は [セットアップ](SETUP.md) と対応する制作記録に保持します。

## 既存作品を再出力する

Git/LFSで取得する画像・音声等と、別途保存する動画を区別します。`production-inputs.json` はローカル動画を含む再現依存の照合一覧です。Gitのみのcloneでは動画が不足する場合があるため、必要な保存動画を元のパス・SHA-256に合わせて復元してから、以下の `--check` と `doctor` を実行します。移送方法は [セットアップ](SETUP.md) を使います。

```powershell
python tools/portable_production.py list
python tools/verify_workspace.py
python tools/update_production_archive.py --check
python tools/portable_production.py doctor
```

共通CLIの `--production` は下表の9エイリアス、またはそれらに対応する現行制作セットIDを受け付けます。他の9作品は版別の専用手順を使います。[作品ごとの重要な条件](#作品ごとの重要な条件)から採用済みの入口を選んでください。

`verify_workspace.py` は、素材の実体、採用ID、明示されたSHA、QA参照と保全方針を点検します。生成中の領域は担当予約に従って除外し、履歴として欠落が明記された根拠や検査範囲の不足は要確認事項として出力します。構造上のエラーがないことを、画風や完成動画の全面的な合格へ読み替えません。

```powershell
$workRoot = if (Test-Path 'D:\') { 'D:\temp\num-num-numbers' } else { Join-Path ([IO.Path]::GetTempPath()) 'num-num-numbers' }
python tools/portable_production.py preview --production four-base --out-dir output/four-base-preview-new --work-dir $workRoot
python tools/portable_production.py render --production four-base --out-dir output/four-base-render-new --work-dir $workRoot
python tools/portable_production.py verify --production four-base --video output/four-base-render-new/paspla-studio-four-ways-to-count-0-to-200-1080p.mp4 --out-dir output/four-base-render-new/qa --work-dir $workRoot
```

出力先の動画、字幕、チャプター、タイトル・概要を確認します。既存完成品を上書きせず、完成MP4を対象とする検査を終えてから採用先を切り替えます。

`preview` / `render` の出力先は未存在のフォルダを指定します。`verify` には確認する `--video` と未使用のQA出力先を渡します。元のレンダーフォルダをQA出力先に使いません。`--timeline`、`--audio`、小鳥用の `--motion-manifest` を省略すると採用原本を使います。別の設計入力を用意した場合は、それぞれを明示して描画・検査できます。

`--timeline` を明示した場合、旧作品の字幕・チャプター・タイトル・概要は自動コピーされません。対応する納品出力ツールへ新しいタイムラインを渡して生成し、完成MP4と内容・時刻が対応することを確認します。

共通CLIの `verify` は、完成MP4の全編デコード、形式・フレーム数・音量、採用音源と最終AACの左右波形・無音・字幕を確認します。全値の字形、桁、個数、受渡し、演技などの追加範囲は作品ごとに異なります。下表の制作記録で、どの検査まで含むか確認し、[完成MP4の検査と登録](#完成mp4の検査と登録)に従って必要な独立検査と実画面確認を補います。

新規ASR・CTC、過去の発音根拠の同一信号への継承、人による試聴は別工程です。`verify` の成功だけを、新規認識や全件試聴の実施記録にしません。

小鳥の現行レシピを新しい場所へ組み直す場合は、次で0〜200の実測計画と音声マスターを作れます。

```powershell
python tools/portable_production.py build-four-base --out-dir output/new-four-base-inputs --design-dir design/new-four-base-inputs --work-dir $workRoot
```

数の範囲、基数、台詞や画面構成を変える新作では、新しい版の設計・準備・描画・字幕・検査ツールを揃えます。既存レシピの数の範囲と場面構成は各制作記録の仕様に対応しています。

同じ原本でもFFmpeg、フォント描画、エンコーダーの版等によってMP4のバイト列やSHA-256は変わることがあります。新しい出力のSHAだけを旧完成品と比較して合否にせず、表示、時刻、フレーム数、音量、音声内容も検査します。

## 作品ごとの重要な条件

現行18制作セットの採用先は [作品台帳](../catalogs/library-v1.json) の `active_production_set_ids` が正本です。次は再出力の入口と、取り違えやすい固有条件の早見表です。範囲・入力・使用ツール・納品先・QAの詳細はリンク先の現行記録を使い、最大の版番号や汎用名のREADMEから推定しません。

| 作品 | 再出力の入口 | 固有条件・現行記録 |
|---|---|---|
| 十進数 | 共通CLI `decimal` | 1〜300の自然読み、青空の庭、採用脚本の効果音。[記録](../design/counting-video-v1/blue-sky-production-run-v002.json) |
| 二進数 | 共通CLI `binary` | 128値・770桁、桁間0.9秒、通常の数の間2秒、十進数看板。[記録](../design/binary-counting-v1/production-run-v005.json) |
| 八進数 | 共通CLI `octal` | 128値・312桁、桁間0.9秒、通常2秒、読みのベースラインと等間隔。[記録](../design/octal-counting-v1/production-run-v002.json) |
| 十六進数 | 共通CLI `hexadecimal` | 0〜7F・240桁、桁間0.9秒、通常2秒、明瞭な単独A。[記録](../design/hexadecimal-counting-v1/production-run-v002.json) |
| 4基数 | 共通CLI `four-base` | 十進0〜200の201値・804表記。通常197境界2秒、説明3境界5秒。[記録](../design/four-base-counting-v1/production-run-v002.json) |
| 偶数 | 共通CLI `even` | 0〜200の101値、通常98境界2秒、説明2境界10秒。旧完成尺6分09秒を保持。[記録](../design/even-counting-v1/production-run-v002.json) |
| 奇数 | 共通CLI `odd` | 1〜299の150値、通常147境界2秒、説明2境界10秒、表示0.12秒先行。[記録](../design/odd-counting-v1/production-run-v002.json) |
| 素数 | 共通CLI `prime` | 2〜997の168値、通常164境界2秒、説明3境界18秒、読了後の進捗。媒体v003／公開文v002を区別。[記録](../design/prime-counting-v1/production-run-v003-publication-v002.json) |
| フィボナッチ | 共通CLI `fibonacci` | F0〜F40の41項・39加算、二つの1、結果0.12秒先行、F20受渡しの88→47px移行。固定AACをcopy。[記録](../design/fibonacci-counting-v1/production-run-v004.json) |
| 平方数 | [専用手順](../design/square-counting-v1/production-motion/render-recipe-v002.json) | 0²〜100²の101項。raw描画後、画素/AACを変えずH.264 VUIを補う二段出力。[記録](../design/square-counting-v1/production-run-v001.json) |
| 三角数 | [現行ブリーフv002](../design/triangular-counting-v1/production-brief-v002.txt) | T0〜T60の61項・60式、二配列から長方形・÷2。合格AACcopyと7納品ファイルの複写。[記録](../design/triangular-counting-v1/production-run-v002.json) |
| コラッツ | [専用手順](../design/collatz-counting-v1/production-v001/reproduction.txt) | 7→1と27→1の129項・127演算。途中計算を項に数えず、1で各旅を止める。[記録](../design/collatz-counting-v1/production-run-v001.json) |
| 2の累乗 | [現行入口v002](../design/powers-of-two-counting-v1/README-production-v002.md) | 2⁰〜2⁶⁴の65項。映像parentとcodec-v003の合格AACを使い、旧AACと取り違えない。[記録](../design/powers-of-two-counting-v1/production-run-v002.json) |
| カタラン数 | [現行入口v004](../design/catalan-counting-v1/PRODUCTION-CURRENT-v004.txt) | C0〜C30の31項。媒体v007と語境界修正済みtimeline／AACを指定。[記録](../design/catalan-counting-v1/production-run-v004.json) |
| 等差数列 | [公開版の入力・実装](PRODUCTION.md#等差数列の公開版再出力) | 初項2・公差3、101項・100加算、最後302。制作v002が採用する映像render/v004と固定入力を使う。[記録](../design/arithmetic-sequence-counting-v1/production-run-v002.json) |
| 等比数列 | [現行専用手順v002](../design/geometric-sequence-counting-v1/production-v002/reproduction.txt) | 初項2・公比3、41項・40演算。現行の比較例Sixと音声入力を指定。[記録](../design/geometric-sequence-counting-v1/production-run-v002.json) |
| トゥエ・モース | [現行入口v003](../design/thue-morse-counting-v1/README-production-v003.md) | 位置0〜255の256項。位置番号と0/1の値、未読セルと読了後の進捗を区別。[記録](../design/thue-morse-counting-v1/production-run-v003.json) |
| リュカ数 | [専用手順](../design/lucas-counting-v1/production-v001/reproduction.txt) | 2、1からL40まで41項・39加算。冒頭の減少、実個数、繰上がり、読了後の進捗。[記録](../design/lucas-counting-v1/production-run-v001.json) |

通常2秒は、前の数の**読み終わりから次の数・式の読み始めまで**の実時間です。桁読み作品の0.9秒を、自然な数詞の語間へ挿入しません。台本上の説明・休憩は作品別の例外として保持し、キャラクターだけの演技追加を理由に間隔を延ばしません。新作の8分原則は[新作の設計](#新作の設計)に従い、過去の完成尺へ遡って適用しません。

合格AACをcopyするレシピでは、音声の再符号化やマスターへの二重ゲインを加えません。再符号化が必要なレシピは、新しい完成AACを検査します。同じ本文や高い波形相関だけで、発音監査を継承しません。

### 作品固有の尺の例

既存の奇数v002は範囲を1〜299へ広げ、確認のある2境界へ各8秒を加えています。数詞150発話の合計をS秒とすると全尺はS+364.40秒です。PCM実測合計171.380916666667秒、音声尺535.780916666667秒に対し、完成MP4の映像尺は535.80秒（16074フレーム・30fps）です。これは作品固有の実測例であり、他作品の尺を決める式にはしません。

### 原音から計画とマスターを組み直す場合

これは既存MP4の固定入力再出力とは別工程です。新しい出力先を使い、新AACには音量・ピーク・発音の検査を行います。以下は他の入口にない明示的な組み直しコマンドです。

```powershell
python tools/build_prime_episode.py --out-dir output/new-prime-inputs --balance-rms-dbfs -19
python tools/build_fibonacci_episode.py --revision-id fibonacci-counting-v003 --speech-manifest output/fibonacci-counting-001-v002/speech/measurements.json --speech-gate output/fibonacci-counting-001-v002/speech/speech-acceptance.json --phonemes output/fibonacci-counting-001-v002/speech/fresh-phonemes.json --codec-corrections output/fibonacci-counting-001-v002/speech/aac-scalar-corrections.json --out-dir output/new-fibonacci-inputs
```

フィボナッチのbuilder既定値はv001互換です。`--revision-id` だけで音源を選ばず、上記4入力を指定します。`--plan-only` ならマスターを作らず選定と時刻を確認できます。T013bの源SHAへ結び付く一定−2.5dB補正は一度だけ適用します。現行の映像・演技は上表のv004レシピから再現します。

### 等差数列の公開版再出力

この公開版は [制作v002](../design/arithmetic-sequence-counting-v1/production-run-v002.json) が採用した映像render/v004です。制作原本で後から採用された腕の改訂とは分け、[公開版の仕様](../design/arithmetic-sequence-counting-v1/production-v002/specification.json) と固定入力を使います。再出力時は出力・QAを未使用の場所へ置き、旧完成品とのバイト一致や新しい完成検査の実施を仮定しません。

| 役割 | 公開済みの入口 |
|---|---|
| 採用タイムライン | [output/arithmetic-sequence-counting-001-v001/audio-build-v003/timeline.json](../output/arithmetic-sequence-counting-001-v001/audio-build-v003/timeline.json) |
| 音声マスター | [output/arithmetic-sequence-counting-001-v001/audio-build-v003/master.wav](../output/arithmetic-sequence-counting-001-v001/audio-build-v003/master.wav) |
| 登録 | [assets/library/characters/hedgehog/generation-batches/arithmetic-production-20261112-01a1cdca-b/registration.json](../assets/library/characters/hedgehog/generation-batches/arithmetic-production-20261112-01a1cdca-b/registration.json) |
| 動作 | [output/arithmetic-sequence-counting-001-v001/render/recheck-visual-candidate-v001/character-motion.json](../output/arithmetic-sequence-counting-001-v001/render/recheck-visual-candidate-v001/character-motion.json) |
| 描画実装 | [tools/render_arithmetic_video.py](../tools/render_arithmetic_video.py) |

rendererの旧既定入力を現行とみなさず、上記タイムライン・登録・動作を明示します。採用AACや最終muxの条件は制作記録から確認し、単なる再描画を過去の最終AAC検査の再実施と扱いません。

### リュカ数v001の専用再出力

[専用再現手順](../design/lucas-counting-v1/production-v001/reproduction.txt)と[納品案内](../design/lucas-counting-v1/production-v001/reproduction.txt)を使います。制作セットv001は描画候補full-v002を採用しており、最大番号から選びません。rendererがmasterから符号化したAACは、採用AACとの全packet・時刻・priming・形式・左右PCMの一致を確認してから発音根拠を継承し、不一致なら新AACを検査します。

### 三角数v002の専用再出力

[現行ブリーフ](../design/triangular-counting-v1/production-brief-v002.txt)の固定入力・AACcopy・7納品ファイルの複写・独立検査を使います。現行の公開文は `output/triangular-counting-001-v002/delivery-description-v001/`、採用根拠は[制作記録](../design/triangular-counting-v1/production-run-v002.json)です。公開文の再出力は次の専用コマンドを使います。

```powershell
python tools/prepare_triangular_delivery_description_v001.py --out-dir output/triangular-delivery-new
```

### 三角数v001（過去版）の専用再出力

当時の入力・出力名・BT709タグ条件はv001ブリーフ（制作原本の参考資料・公開版には未同梱: `design/triangular-counting-v1/production-brief-v001.md`）、採否・検査はv001制作記録（制作原本の参考資料・公開版には未同梱: `design/triangular-counting-v1/production-run-v001.json`）に残します。現行v002の手順と混ぜず、旧媒体・コード・当時のQAを上書きしません。

## 制作で得た共通メモ

次の知見を新作と改訂に使い、作品別の判断と根拠は [制作ブリーフ](../templates/production-brief.md) へ記入します。個別作品の原画数、動作回数、静止秒数、中間姿勢の保持時間、検査件数、表示px、検出・抽出用の数値を、一律の目標や閾値にしません。共通仕様で定めた受入条件・許容差は保ち、個別例を追加したことを理由に緩めません。

1. **仕草は教材と発話から決める。** 台詞ID・出来事・静かな区間に演技を対応させ、通常の読み速度や間隔を延ばさない。[演技の設計](#キャラクター演技と不足素材) に記録する。
2. **正常な形と、伝わる演技を分ける。** 前後の姿勢で動きの軸と深まり、関節・掌・内部線・前後関係を確認する。端の姿勢や外周一致だけで途中の自然さを判断しない。詳細は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md#腕手などの部品演技) を使う。
3. **良好な素材を維持し、必要箇所だけ比較する。** 不足・欠点と改善条件を先に決め、新規案が明確に良く退行もない場合だけ採用する。同等・不明・悪化は既存維持とし、[画像管理仕様の採用判断](IMAGE-ASSET-MANAGEMENT.md#選択から採用への反映) に根拠を結び付ける。
4. **短片で直し、完成品で新たに確認する。** [本編前の確認](#本編前の圧縮動作確認) で素材・登録・実装・時刻を固定し、変更時は再確認する。静止・離散キー・圧縮短片・完成作品・実時間視聴の確認範囲を混ぜない。
5. **検査する側も検証する。** 件数は今回の入力から数え、部位別ノイズ・近接要素・AA縁を実画と正例・負例で校正する。[観測方法と対照検査](#観測方法と対照検査) と [配置仕様](LAYOUT-ALIGNMENT.md) を使う。
6. **音声の同一性と発音の根拠を結ぶ。** [同一信号への継承条件](#同一信号への発音根拠の継承) で、今回の波形・境界検査、継承した根拠、新規認識・試聴の範囲を分ける。
7. **版名と採用先を混同しない。** 音声入力の版、視覚上の親版、出力試行、QA、公開文はそれぞれパス・SHAを明記します。同じ版番号や最大版数だけで選びません。採用前の既定エイリアスは旧版を指すことがあるため、新版の入力は明示し、プレビュー・フレーム準備・全編生成を区別します。採用後の既定レシピも確認し、版別CLIの引数は実際のヘルプで調べます。
8. **証拠は確定後に一方向へ束ねる。** [固定と再試行](#証拠の固定と再試行) に従い、相互参照や書込み途中の記録を避け、失敗結果・固定原本・新しい試行を保全する。

根拠となる個別記録は次のとおりです。ここで実施した方法や件数を、全作品の必須方式・合格値にはしません。

| 知見の根拠 | 記録 |
|---|---|
| 演技・構図と静穏区間の比較 | [素数v003](../design/prime-counting-v1/production-review-v003.txt) |
| 姿勢・時刻・音声継承・証拠の保全 | [フィボナッチv004の制作レビュー](../design/fibonacci-counting-v1/production-review-v004.txt)・再検査（制作原本の参考資料・公開版には未同梱: `design/fibonacci-counting-v1/recheck-v004-20261112-0653/recheck-report.txt`） |
| 腕の自然さ、内部線、短片から完成版の再確認 | 等差数列v005の制作レビュー（制作原本の参考資料・公開版には未同梱: `design/arithmetic-sequence-counting-v1/production-review-v005.txt`）・完成MP4の演技確認（制作原本の参考資料・公開版には未同梱: `design/arithmetic-sequence-counting-v1/arm-motion-review-20261113-v001/video/final-v007-artistic.json`） |
| 部位別の検出校正、近接文字の抽出と対照 | 動作検出の校正（制作原本の参考資料・公開版には未同梱: `design/arithmetic-sequence-counting-v1/arm-motion-review-20261113-v001/video/observer-calibration-report-v001.json`）・数値表示の最終確認（制作原本の参考資料・公開版には未同梱: `output/arithmetic-sequence-counting-001-v001/arm-motion-review-20261113-v001/content/final-v003/content-final-summary.json`） |
