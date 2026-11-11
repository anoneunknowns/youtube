# キャラクター素材の利用案内

機械可読の入口は [`catalogs/character-library-v1.json`](../../catalogs/character-library-v1.json) です。採用版、通常姿、動作、登録座標、確認記録をこの台帳から辿ってください。フォルダの最大バージョン番号は採用版の意味ではありません。

新しい動物7種類には通常姿7枚と基本表情・動作42枚があります。既存のクマ、ウサギ、とら、小鳥を含む11種類でタッチを確認しています。人が見る一覧は [通常姿](collections/animal-stock/v001/index.html) と [基本表情・動作](collections/animal-motions/v001/index.html) です。

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

`export` の出力先は作業環境に合わせて変更できます。ZIPには `character-library/` を起点に11キャラクター、通常姿・動作の2collection、AI向け台帳とファイル一覧、検証・描画ツール、Pillowの依存指定を含みます。動画全制作のcatalogを必要とせずに利用できます。

別PCではZIPを展開し、その中の `character-library/` へ移動して実行します。

```powershell
python -m pip install -r requirements.txt
python tools/character_library.py verify
python tools/character_library.py list --json
```

PNGだけを抜き出さず、台帳、登録情報、生成条件、確認記録も一緒に保管し、相対配置を維持してください。各コマンドはツールがあるcheckoutを基準に動き、別の配置を指定する場合は `python tools/character_library.py --root <展開先> verify` のように指定できます。`refresh` は素材の採用先や保管ファイルを更新した際の台帳・ファイル一覧の再構築用で、通常の利用には不要です。

## 採用する通常姿と動作

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

各動物の `motions/v001/registration.json` を読みます。`frames` の `path` が透過PNG、`anchor_px` がそのセル内の足元支点、`common_reference_height_px` が全ポーズ共通の立ち姿基準高です。

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
