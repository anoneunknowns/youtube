# キャラクター素材の利用案内

機械可読の入口は [`catalogs/character-library-v1.json`](../../catalogs/character-library-v1.json) です。採用版、通常姿、動作、登録座標、確認記録をこの台帳から辿ってください。フォルダの最大バージョン番号は採用版の意味ではありません。

全生成バッチの用途・担当・候補・品質指摘は [画像管理一覧](character-assets.html) へまとめています。[管理設定](../../catalogs/character-asset-management-v1.json) と [管理在庫](../../catalogs/character-asset-registry-v1.json) は、通常姿や動画の採用先とは別です。作品専用のカンガルー・シャム猫も管理し、生成中の担当領域は予約付きの保留として追跡します。

拡充270姿勢とアイキャッチ144姿勢の [詳細な画風監査](collections/character-style-audit/v001/index.html) では、輪郭・色・頭身・瞳等の修正候補が見つかっています。過去のファイル整合・透過検査の合格は維持し、現在の品質指摘を管理設定へ重ねています。生成・整理の規約とコマンドは [画像管理仕様](../../docs/IMAGE-ASSET-MANAGEMENT.md) を参照してください。

素数動画v003のカンガルーは、[作品用の腕リグ・姿勢素材](characters/kangaroo/animations/prime-v002/README.txt)を明示指定します。入口は同フォルダの `registration.json` と、作品台帳 `catalogs/library-v1.json` の `kangaroo-prime-animation-v002` です。手振り・思考・展示案内・拍手の12原画を新規生成し、良好な既存15原画と合わせて27原画・29状態（別名2つを含む）を登録しました。立位の手の差分だけを通常姿へ合成して頭・胴体の跳ねを防ぎ、着座・伸び・復帰は共通縮尺の既存原画を使います。従来の通常姿・汎用キーポーズ・prime-v001は維持します。タイミングは作品の `kangaroo-motion.json`、実MP4の確認結果は `design/prime-counting-v1/production-review-v003.txt` を参照してください。

11種類の採用通常姿と既存素材に加え、クマ以外の10種類へ各27姿勢、計270枚の表情・動作を新規生成しました。[拡充素材一覧](collections/character-expansion/v001/index.html) から明色・暗色の比較図、手振り・ジャンプ・着座の確認用GIF、登録情報へ進めます。従来の [通常姿](collections/animal-stock/v001/index.html) と [基本表情・動作42枚](collections/animal-motions/v001/index.html) も保全しています。

大きい表示枠の哺乳類8種には、さらに [アイキャッチ素材](collections/character-eyecatches/v001/index.html) があります。対象はクマ、ウサギ、とら、シャム猫、レッサーパンダ、ミーアキャット、カンガルー、ハリネズミです。紅茶を飲む・ジャンプ・おじぎ・小さなダンスの4動作を、各18姿勢、合計144枚の新規透過PNGと32個の動作別確認GIFで用意しています。指定された昆虫・植物・鳥系・ハムスターは対象外です。

アイキャッチは各キャラクターの `eyecatches/v001/registration.json` と台帳の `eyecatch_key_poses` を参照します。汎用ローダーでは `eyecatch/tea_sip`、`eyecatch/jump_air`、`eyecatch/bow_deep`、`eyecatch/dance_left` のように明示指定します。通常姿、従来動作、`expanded/` の選択は維持しています。元シート・正確なプロンプト・参照ハッシュ・校正・足支点も同じフォルダに保管しています。

紅茶の確認ループはカップを持った姿勢から始めて戻る構成です。カップのない通常姿と直結する際の登場・退場は、使用するシーンで設計してください。ジャンプの離地・空中は登録した推定地面を使い、足を接地させたり、素材に含まれる浮きをもう一度加えたりしません。GIFは離散キーポーズの確認用で、補間・音声同期・動作頻度・完成画面の余白は各シーンで確認します。

拡充分は各キャラクターの `motions/v002/registration.json`、採用先は機械可読台帳を参照してください。クマの実素材にある12反応、手振り、着座、伸び、休憩を基準に、中間姿勢・拍手の開き側・座った視線差分も追加しています。鳥は翼での挨拶と低い休憩姿勢です。原画の採用先と既存完成動画は変更していません。

新規27姿勢の構成は次の通りです。

- 反応9枚：生成した通常姿、瞬き、ため、軽い跳ね、考える、ひらめき、驚き、再挑戦、固有の仕草。
- 動作9枚：成功の準備・空中・着地、喜び、拍手の開き側、手振りの低位置・内側・外側・休止。
- 姿勢9枚：着座途中、座位休止、伸び途中・伸び、居眠り、座位の上向き・横向き視線、起立途中、控えめな下向きの頭の姿勢。

汎用ローダーの `neutral` と既存のポーズ名は従来どおりです。追加分は台帳の `expanded_key_poses` と、ローダーの `expanded/blink`、`expanded/wave_low`、`expanded/seated_stretch` などから明示的に選びます。追加シートの校正用通常姿は `expanded/neutral` です。ウサギ・とら・小鳥の旧専用atlasも元の場所に残っています。

```powershell
python tools/character_library.py preview --character siamese-cat --pose expanded/wave_low --height 430 --output ./siamese-cat-expanded-wave.png
```

拡充素材は3つの元生成シートそれぞれで立ち姿相当の基準高を校正しています。`scale = desired_body_height / frame.reference_height_px` を使い、同じシート内では全姿勢へ同じ等方縮尺を適用してください。座位を外接矩形の高さで拡大しません。空中姿勢の支点は周囲の接地姿勢から推定した地面であり、浮いた足の位置へ接地させません。姿勢間の細かな造形差や補間、発話との同期は使用するシーンで調整・確認します。GIFは離散キーポーズの確認用です。

## 取得・検証

Pythonを利用できる環境で、リポジトリのルートから実行します。Pillowの依存指定はルートの `requirements.txt` にあります。

今回の検証環境はPython 3.15.2、Pillow 13.0.0です。

```powershell
git lfs pull
python -m pip install -r requirements.txt
python tools/character_library.py list
python tools/character_library.py list --json
python tools/character_library.py verify
python tools/character_library.py preview --character onagadori --pose wing_up --height 280 --output D:/temp/onagadori-wing-up.png
python tools/character_library.py export --output D:/temp/num-num-character-library.zip
```

`export` の出力先は作業環境に合わせて変更できます。ZIPには `character-library/` を起点に11キャラクター、通常姿・従来動作・拡充動作・アイキャッチの4collectionに加え、管理在庫・担当予約・保全した画風監査、検証・描画ツール、Pillowの依存指定を含みます。作品固有の採用根拠は管理資料内のスナップショットで保全し、動画全制作のcatalogを必要とせずに利用できます。生成中のバッチは確定原画としてZIPへ混ぜず、担当付きの保留を記録します。

別PCではZIPを展開し、その中の `character-library/` へ移動して実行します。

```powershell
python -m pip install -r requirements.txt
python tools/character_library.py verify
python tools/character_library.py list --json
```

PNGだけを抜き出さず、台帳、登録情報、生成条件、確認記録も一緒に保管し、相対配置を維持してください。各コマンドはツールがあるcheckoutを基準に動き、別の配置を指定する場合は `python tools/character_library.py --root <展開先> verify` のように指定できます。`refresh` は素材の採用先や保管ファイルを更新した際の台帳・ファイル一覧の再構築用で、通常の利用には不要です。

## 採用する通常姿と従来の基本動作

次の表は従来42枚の参照版です。追加270枚はクマ以外の10種類すべての `motions/v002` にあります。

| ID | 名前 | 採用した通常姿 | 動作 |
|---|---|---|---|
| `siamese-cat` | シャム猫 | `sources/v005` | `motions/v001` |
| `red-panda` | レッサーパンダ | `sources/v001` | `motions/v001` |
| `meerkat` | ミーアキャット | `sources/v004` | `motions/v001` |
| `kangaroo` | カンガルー | `sources/v002` | `motions/v001` |
| `hedgehog` | ハリネズミ | `sources/v003` | `motions/v001` |
| `fairy-pitta` | ヤイロチョウ | `sources/v001` | `motions/v001` |
| `onagadori` | オナガドリ | `sources/v002` | `motions/v001` |

表のディレクトリは `assets/library/characters/<ID>/` からの相対位置です。正確なファイルパスとハッシュは台帳を優先します。未採用の比較案は履歴として残してあり、制作時の候補に自動選択しません。

哺乳類5種の6ポーズは `blink`、`greet`、`think`、`aha`、`cheer`、`species_action` です。固有動作は順に猫の毛づくろい、レッサーパンダの尾を抱く仕草、ミーアキャットの見張り、カンガルーの接地した屈伸、ハリネズミの控えめに身をかがめる仕草です。

鳥2種は `blink`、`wing_half`、`wing_up`、`peck_half`、`peck_down`、`cheer` です。羽ばたきと下向きの仕草には確認用GIFもあります。`peck_down` はくちばしを下げる姿勢で、地面への実接触を保証する素材ではありません。280px身体高の比較では、くちばし先と足元の間隔はヤイロチョウで約25〜28px、オナガドリで約5〜10pxです。

## 描画に使う登録情報

従来42枚では各動物の `motions/v001/registration.json` を読みます。`frames` の `path` が透過PNG、`anchor_px` がそのセル内の足元支点、`common_reference_height_px` が全ポーズ共通の立ち姿基準高です。拡充270枚では `motions/v002/registration.json` の各frameの `reference_height_px` とシート別の校正記録を使用します。

```text
scale = desired_body_height / common_reference_height_px
draw_x = desired_support_x - anchor_px[0] * scale
draw_y = desired_ground_y  - anchor_px[1] * scale
```

同じ動物の全動作へ同じ等方縮尺を使ってください。屈伸やついばみ姿勢を、その都度の見えている高さで拡大すると体格が跳ねます。通常姿には通常姿の登録済み身体高と支点を使い、両者を同じ表示身体高へ合わせます。430pxの哺乳類と280pxの鳥は今回の比較尺度であり、動画の固定サイズ指定ではありません。

オナガドリは身体と長い尾の範囲を別々に登録しています。身体で縮尺を決め、尾の全幅が収まる配置を確保してください。尾全体を狭い枠に収めるために身体を縮めたり、尾の末端を足支点に使ったりしないでください。

素材はキーポーズです。新しい動画では通常姿への入口・出口、動作の間隔、補間、画面内の余白をそのシーンで確認します。既存4キャラクターには従来の専用登録・描画処理があるため、新7種類のセル構成をそのまま当てはめません。

## 原画と記録の保管

- 採用原画、生成シート、切り出しPNGを上書きしません。修正版・派生ポーズは新しい版へ保存し、台帳の採用先を明示して更新します。
- 保存済みの42枚は生成シートからの無拡縮・無描き替えのセル抽出です。輪郭、色、アルファを機械的に変更しません。
- `generation-prompt.txt`、`generation-input.json`、元シート、入力参照のハッシュ、`source-manifest.json` または `registration.json` を一緒に残します。
- 台帳・登録情報のプロジェクト相対パスを実利用の参照に使います。各manifest内のローカルファイル名は、そのmanifestがあるディレクトリを基準に解決します。
- `original_generated_file`、`original_input_path`、過去のQAにある `C:/...` や `D:/temp/...` は作成時の履歴です。現在のPCに同じ絶対パスが存在する前提で読み込みません。`registration-input.json` も当時の実行条件の保存です。再登録する際は、現PCの実入力から新しい設定を作成してください。
- 生成画像にはアルファ最大254のものもあります。透過性の不備とは限りません。アルファ0に残るRGBが単純なプレビューで茶色や鮮色に見える場合は、正しくアルファ合成した明色・暗色背景で判断します。見えないRGBやアルファを削って原画を改変しません。

ヤイロチョウの指定は高知県指定天然記念物、土佐のオナガドリは国指定特別天然記念物として調査しています。オナガドリの今回の原画は白色種です。根拠は [調査記録](collections/animal-stock/v001/research.json) にあり、外部写真はストック素材へ取り込んでいません。この案内は新しい再配布ライセンスを付与しません。

最終チェックの記録は各collectionの `qa-evidence/` に保存しています。今後の更新後も `python tools/character_library.py verify` を実行して、台帳・原画・切り出し・参照の整合を確認してください。
