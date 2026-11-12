# キャラクター素材の利用案内

<!-- BEGIN UNIFIED-ASSET-ENTRY -->
## 新旧19種類の共通配置

既存キャラクター11種類と背景素材8種類は、[`catalogs/asset-library-current-v1.json`](../../catalogs/asset-library-current-v1.json)を共通の入口にします。各IDの `assets/library/characters/<id>/current/` に `asset.json`、`neutral.png`、`poses/<namespace>/<pose>.png`、`clips.json` があります。各画像のパスは `asset.json` がある `current/` から解決し、元原画を示す `source_path` はプロジェクトのルートから解決してください。

`current/` は台帳が選んだ通常姿・ポーズを無改変コピー、または採用atlas領域を無拡縮で切り出した共通窓口です。従来の原画・登録・過去の採用は元の場所で保全します。名前空間は `basic/`、`expanded/`、`eyecatch/`、`gimmick/` で、動作順・時間・ループ・再生効果は `clips.json` を参照します。`character_library.py` の従来基本ポーズは接頭辞なし、背景素材は `gimmick/<pose>` で選択します。

採用台帳を更新した管理担当は、次の順で共通入口を再構築・確認します。既存PNGと内容が異なるときは、期待ハッシュを書き換えず採用元と派生先を調べてください。

```powershell
python tools/unified_asset_library.py build
python tools/unified_asset_library.py verify
```

## 背景素材8種類の表示と動作

[背景素材ギャラリー](collections/background-gimmicks/v001/index.html)から、通常姿、49姿勢、28動作の実GIF、登録情報、原画・生成条件、各素材の `current/asset.json` へ進めます。[一覧PNG](collections/background-gimmicks/v001/overview.png)と[カードの配置検査](collections/background-gimmicks/v001/qa-evidence/gallery-alignment-v001.json)も保存しています。

| ID | 素材 | 最大表示の目安と対象 | 登録・原寸確認の入口 |
|---|---|---|---|
| `grass` | 草 | 通常姿の幅600pxを基準 | [`geometry-qa.json`](characters/grass/motions/v001/geometry-qa.json) |
| `flower-bed` | 花壇 | 通常姿の幅520pxを基準 | [`geometry-qa.json`](characters/flower-bed/motions/v001/geometry-qa.json) |
| `airplane` | 飛行機 | 水平姿勢の全幅360px | [`qa-v001.json`](characters/airplane/motions/v001/qa-v001.json) |
| `rocket` | ロケット | 炎を除いた胴体高300px | [`qa-v001.json`](characters/rocket/motions/v001/qa-v001.json) |
| `helicopter` | ヘリコプター | 主ローターの非短縮時の展開幅500px | [`qa-v001.json`](characters/helicopter/motions/v001/qa-v001.json) |
| `butterfly` | 蝶 | 翼全開時の幅200px | [`qa-registration-v001.json`](characters/butterfly/motions/v001/qa-registration-v001.json) |
| `ladybug` | てんとう虫 | 脚・飛行翼を除いた甲羅幅140px | [`qa-registration-v001.json`](characters/ladybug/motions/v001/qa-registration-v001.json) |
| `rainbow` | 虹 | 完全なアーチの全幅1200px | [`qa-registration-v001.json`](characters/rainbow/motions/v001/qa-registration-v001.json) |

これらの幅と、ローダーの `--height` が表す登録基準高は別の量です。各frameの `reference_height_px` を使って `scale = desired_reference_height / reference_height_px` とし、同じ校正済みシート内では共通縮尺を維持します。蝶は `--height 77` で全開翼幅約198px、てんとう虫は `--height 151` で甲羅幅約140px、虹は `--height 624` で全幅約1200pxです。画素不足を拡大や輪郭清掃で埋めず、使用倍率を変えるときは原寸で再確認してください。

草・花壇は根元や土台、飛行機・ヘリ・昆虫は登録された胴体等の中心、ロケット・虹は基部の支点を使います。揺れた葉・広げた翼・長い炎・回転翼の見かけ幅による個別fitはしません。草・花壇の揺れや昆虫の展開翼は通常姿より広がるため、その全範囲の余白を確保します。虹の出現・消去・光の移動は、未改変の完全形PNGを共通支点・共通縮尺で再生する効果です。

ギャラリーのサムネイルは通常姿を独立に縮小した表示用画像です。実動作では登録済み支点と身体基準を使い、GIFの離散キーポーズ確認と、作品内の補間・経路・音声同期・数値や字幕との余白・連続動作の確認を分けてください。
<!-- END UNIFIED-ASSET-ENTRY -->

機械可読の入口は [`catalogs/character-library-v1.json`](../../catalogs/character-library-v1.json) です。採用版、通常姿、動作、登録座標、確認記録をこの台帳から辿ってください。フォルダの最大バージョン番号は採用版の意味ではありません。採用中の `v001` や、現行作品が継承する以前の版の入力も現在の利用対象です。

GitHubの公開範囲は[公開対象一覧](../../catalogs/github-publication-v1.json)の `files`、素材パッケージの範囲は同じ一覧の `character_library_files` です。現行の採用素材と必要な入力・資料を公開し、未使用の旧版・不採用候補・過去の完成品・動画ファイルはローカル保管とします。台帳・登録情報・管理資料には旧版のパスやハッシュも来歴として残ります。公開対象一覧にない履歴参照は、GitHubや素材ZIPで取得できるファイルを示しません。

担当・用途・品質指摘は[画像管理一覧](character-assets.html)、[管理設定](../../catalogs/character-asset-management-v1.json)、[管理在庫](../../catalogs/character-asset-registry-v1.json)を参照してください。管理資料の収録、過去の採用、現在の画風・動作品質は個別に確認します。生成・登録の規約は[画像管理仕様](../../docs/IMAGE-ASSET-MANAGEMENT.md)にあります。

## 現行の共通素材

11種類の採用通常姿、従来42姿勢、クマ以外10種類の拡充270姿勢、哺乳類8種類のアイキャッチ144姿勢を登録しています。人が見る入口は[通常姿](collections/animal-stock/v001/index.html)、[基本表情・動作](collections/animal-motions/v001/index.html)、[拡充素材](collections/character-expansion/v001/index.html)、[アイキャッチ](collections/character-eyecatches/v001/index.html)です。

通常姿は台帳の `neutral`、従来42姿勢は `key_poses`、拡充は `expanded_key_poses`、アイキャッチは `eyecatch_key_poses` を使います。追加分は `expanded/wave_low` や `eyecatch/tea_sip` のように名前空間を明示します。従来の通常姿やポーズを、追加素材の通常姿へ自動的に置き換えません。

拡充は各キャラクターの `motions/v002/registration.json`、アイキャッチは `eyecatches/v001/registration.json` を参照します。拡充には反応・手振り・ジャンプ・着座・伸び・視線等、アイキャッチには紅茶・ジャンプ・おじぎ・小さなダンスがあります。[画風監査](collections/character-style-audit/v001/index.html)には輪郭・色・頭身・瞳等の修正候補が残っています。利用する素材の `quality_reviews` と確認画像を読み、整合検査の合格と画風・動作の判断を分けてください。

カンガルーやシャム猫の作品用素材は、[`catalogs/library-v1.json`](../../catalogs/library-v1.json)の現行作品と制作記録から選びます。素数v003用カンガルーの入口は [`animations/prime-v002/registration.json`](characters/kangaroo/animations/prime-v002/registration.json)です。作品用の腕リグやタイミングを、汎用ローダーのポーズ名へ読み替えません。

## 取得・検証

Pythonを利用できる環境で、リポジトリのルートから実行します。Pillowの依存指定はルートの `requirements.txt` にあります。初回cloneで素材だけを取得する手順は[READMEのAI向け案内](../../README.md#他プロジェクトのai向けキャラクター素材の場所と利用方法)を参照してください。

```powershell
git lfs pull --include="assets/library/characters/**,assets/library/collections/**,assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf" --exclude=""
python -m pip install -r requirements.txt
python tools/character_library.py list
python tools/character_library.py list --json
python tools/character_library.py verify
python tools/character_library.py preview --character onagadori --pose wing_up --height 280 --output ../onagadori-wing-up.png
python tools/character_library.py preview --character siamese-cat --pose expanded/wave_low --height 430 --output ../siamese-cat-wave.png
python tools/character_library.py preview --character red-panda --pose eyecatch/tea_sip --height 430 --output ../red-panda-tea.png
python tools/character_library.py export --output ../num-num-character-library.zip
```

出力先には、既存ファイルと重ならない場所を指定してください。公開版の `verify` と `export` は公開対象一覧の `character_library_files` に従います。ZIPには `character-library/` を起点に、採用画像・登録情報・生成条件・公開した確認資料・台帳・検証描画ツール・依存指定を収録し、ZIPの `.sha256`・`.json` も出力します。未使用の旧版・候補・動画は含めません。素材台帳と相対配置を維持し、作品全体やローカルの全履歴を取得せずに利用できます。

公開データをすべて取得したcheckoutの検査には `python tools/verify_github_publication.py` を使います。素材だけを取得した場合は `character_library.py verify` で確認します。`verify_workspace.py`、`manage_character_assets.py check`、`update_production_archive.py --check` は、旧資料・動画も保管したローカル制作環境向けの検査です。

別PCではZIPを展開し、その中の `character-library/` へ移動して実行します。

```powershell
python -m pip install -r requirements.txt
python tools/character_library.py verify
python tools/character_library.py list --json
```

PNGだけを抜き出さず、台帳、登録情報、公開対象一覧、生成条件、確認記録も一緒に保管し、相対配置を維持してください。各コマンドはツールがあるcheckoutを基準に動き、別の配置を指定する場合は `python tools/character_library.py --root <展開先> verify` のように指定できます。利用側で `refresh` を実行して期待ハッシュを書き換えず、取得漏れや参照元を調べてください。

## 採用する通常姿と従来の基本動作

次の7種類には従来の基本動作が各6枚あります。拡充・アイキャッチは上記の別登録を使います。

| ID | 名前 | 採用した通常姿 | 動作 |
|---|---|---|---|
| `siamese-cat` | シャム猫 | `sources/v005` | `motions/v001` |
| `red-panda` | レッサーパンダ | `sources/v001` | `motions/v001` |
| `meerkat` | ミーアキャット | `sources/v004` | `motions/v001` |
| `kangaroo` | カンガルー | `sources/v002` | `motions/v001` |
| `hedgehog` | ハリネズミ | `sources/v003` | `motions/v001` |
| `fairy-pitta` | ヤイロチョウ | `sources/v001` | `motions/v001` |
| `onagadori` | オナガドリ | `sources/v002` | `motions/v001` |

表のディレクトリは `assets/library/characters/<ID>/` からの相対位置です。正確なファイルパスとハッシュは台帳を優先します。未採用の比較案はローカルの履歴として保管し、公開対象や採用版へ自動的に含めません。

哺乳類5種の6ポーズは `blink`、`greet`、`think`、`aha`、`cheer`、`species_action` です。固有動作は順に猫の毛づくろい、レッサーパンダの尾を抱く仕草、ミーアキャットの見張り、カンガルーの接地した屈伸、ハリネズミの控えめに身をかがめる仕草です。

鳥2種は `blink`、`wing_half`、`wing_up`、`peck_half`、`peck_down`、`cheer` です。羽ばたきと下向きの仕草には確認用GIFもあります。`peck_down` はくちばしを下げる姿勢で、地面への実接触を保証する素材ではありません。280px身体高の比較では、くちばし先と足元の間隔はヤイロチョウで約25〜28px、オナガドリで約5〜10pxです。

## 描画に使う登録情報

従来42姿勢は各動物の `motions/v001/registration.json` を読みます。`frames` の `path` が透過PNG、`anchor_px` がそのセル内の足元支点、`common_reference_height_px` が全ポーズ共通の立ち姿基準高です。拡充・アイキャッチは各frameの `reference_height_px` とシート別の校正記録を使います。

```text
scale = desired_body_height / common_reference_height_px
draw_x = desired_support_x - anchor_px[0] * scale
draw_y = desired_ground_y  - anchor_px[1] * scale
```

同じ動物の同じ校正済みシート内では、全姿勢へ共通の等方縮尺を使ってください。拡充・アイキャッチは `scale = desired_body_height / frame.reference_height_px` です。屈伸や着座・ついばみ姿勢を、その都度の見えている高さで拡大すると体格が跳ねます。通常姿には通常姿の登録済み身体高と支点を使い、同じ表示身体高へ合わせます。ウサギの通常姿は台帳の `image_region_px` を切り出します。430pxの哺乳類と280pxの鳥は比較尺度であり、動画の固定サイズ指定ではありません。

オナガドリは身体と長い尾の範囲を別々に登録しています。身体で縮尺を決め、尾の全幅が収まる配置を確保してください。尾全体を狭い枠に収めるために身体を縮めたり、尾の末端を足支点に使ったりしないでください。

素材はキーポーズです。新しい動画では通常姿への入口・出口、動作の間隔、補間、画面内の余白をそのシーンで確認します。既存4キャラクターには従来の専用登録・描画処理があるため、新7種類のセル構成をそのまま当てはめません。

空中姿勢は登録された支点の種類に従います。周囲の接地姿勢から推定した地面を使う素材へ、作品側の浮きを二重に加えません。紅茶の確認GIFはカップを持った姿勢へ戻るループなので、カップのない通常姿との接続には登場・退場の設計が必要です。GIFの確認範囲と、完成画面の連続動作・音声同期・余白の検査を分けてください。

## 原画と記録の保管

- 採用原画、生成シート、切り出しPNGを上書きしません。修正版・派生ポーズは新しい版へ保存し、台帳の採用先を明示して更新します。
- 保存済みの42枚は生成シートからの無拡縮・無描き替えのセル抽出です。輪郭、色、アルファを機械的に変更しません。
- `generation-prompt.txt`、`generation-input.json`、元シート、入力参照のハッシュ、`source-manifest.json` または `registration.json` を一緒に残します。
- 台帳・登録情報のプロジェクト相対パスを実利用の参照に使います。各manifest内のローカルファイル名は、そのmanifestがあるディレクトリを基準に解決します。
- `original_generated_file`、`original_input_path`、過去のQAにある `C:/...` や `D:/temp/...` は作成時の履歴です。現在のPCに同じ絶対パスが存在する前提で読み込みません。`registration-input.json` も当時の実行条件の保存です。再登録する際は、現PCの実入力から新しい設定を作成してください。
- 旧版・候補・動画の来歴は元のパスとハッシュを維持します。公開対象外の原本はローカル保管であり、管理資料へ記載されたことをGitHubへの収録と解釈しません。
- 生成画像にはアルファ最大254のものもあります。透過性の不備とは限りません。アルファ0に残るRGBが単純なプレビューで茶色や鮮色に見える場合は、正しくアルファ合成した明色・暗色背景で判断します。見えないRGBやアルファを削って原画を改変しません。

ヤイロチョウの指定は高知県指定天然記念物、土佐のオナガドリは国指定特別天然記念物として調査しています。オナガドリの今回の原画は白色種です。根拠は [調査記録](collections/animal-stock/v001/research.json) にあり、外部写真はストック素材へ取り込んでいません。この案内は新しい再配布ライセンスを付与しません。

最終チェックの記録は各collectionの `qa-evidence/` に保存しています。今後の更新後も `python tools/character_library.py verify` を実行して、台帳・原画・切り出し・参照の整合を確認してください。
