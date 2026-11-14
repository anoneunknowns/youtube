# Num-Num Numbers — 画像素材ライブラリと動画制作

> この公開版の現行作品と参照先は、同梱のカタログ・公開profileに合わせています。制作原本専用の資料は「公開版には未同梱」と明示します。全履歴用のarchive検査やdoctorには、未同梱の再現依存一覧・原本資料・ローカル動画を別途戻す必要があり、cloneだけで揃うとは扱いません。

Paspla StudioのNum-Num Numbersで使う、透過画像・ポーズ・動作をまとめた素材ライブラリです。全120種類を同じ台帳とフォルダ構造で管理しています。他のプロジェクトでは、使いたいPNGを1枚選ぶところから利用できます。

画像の入口は[素材一覧・利用ガイド](assets/library/README.md)、AI向けの機械可読な入口は[共通素材台帳](catalogs/asset-library-current-v1.json)です。[素材を扱うAIへの指示](assets/library/AGENTS.md)には、画像の選び方・支点・共通縮尺・出典の扱いをまとめています。

このリポジトリでは数を学ぶYouTubeシリーズの企画、英語台本、背景、採用音声、描画・検査ツール、制作記録も管理します。制作する場合は[セットアップ](docs/SETUP.md)、[制作手順](docs/PRODUCTION.md)、[ファイル構成](docs/PROJECT-MAP.md)を参照してください。

## 作業別の仕様の入口

| 作業 | 正本・手順 |
|---|---|
| 画像・ポーズを使う | [素材利用ガイド](assets/library/README.md)と[共通素材台帳](catalogs/asset-library-current-v1.json) |
| 画像を生成・リメイク・比較・採用する | [画像管理仕様](docs/IMAGE-ASSET-MANAGEMENT.md) |
| 枠内配置・足支点・実描画を検査する | [配置仕様](docs/LAYOUT-ALIGNMENT.md) |
| 新作を設計する・既存作品を再出力する | [制作仕様](docs/PRODUCTION.md)と[制作ブリーフ](templates/production-brief.md) |
| 環境を準備する | [セットアップ](docs/SETUP.md)と[ツールの確認記録](docs/TOOLCHAIN.md) |
| GitHubへ公開する・取得実体を検証する | [GitHub公開仕様](docs/GITHUB-PUBLICATION.md) |
| 保存先と仕様・台帳の役割を調べる | [ファイル構成と正本](docs/PROJECT-MAP.md) |

共通の受入条件は各仕様に、作品ごとの数値・採用先・実施したQAは制作記録に残します。過去の採用・検査記録と当時のパス・SHAは残し、不要な旧媒体を一律に保管し続けません。整理の優先度は[不要旧版の削除手順](docs/IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合)に従い、過去の採用や確認範囲を書き換えません。

## 他プロジェクトのAI向け：キャラクター素材の場所と利用方法

### 素材を選ぶ

120種類・通常姿120枚と各種ポーズ・顔アイコン、計1699ファイルの透過PNGを、[一つの素材一覧](assets/library/README.md)から選べます。擬人化した動物キャラ、鳥のように簡略化した動物の小物、植物・乗り物・昆虫・虹を、同じ台帳とフォルダ構造で扱います。使う画像と動作の有無は各IDの `asset.json`・`clips.json` から確認してください。

動画の基本セットに対応する96種類は、瞬き・挨拶・左右案内・考える／気づく・喜ぶ・固有のしぐさを `video/` から選べます。ポーズと7つの動作レシピの使い方は[素材ガイド](assets/library/README.md#動画で使う基本セット)を参照してください。

各IDは同じ構造です。通常姿はそのまま使えるPNGで、シートからの切り出し作業は済んでいます。

```text
catalogs/asset-library-current-v1.json
assets/library/characters/<id>/current/
  asset.json
  neutral.png
  poses/<namespace>/<pose>.png
  clips.json
  icons/<name>.png（対応する素材のみ）
```

| 使いたいもの | 読む場所 |
|---|---|
| 画像を1枚使う | 素材一覧のPNGリンク、または各IDの `current/neutral.png` |
| 表情・姿勢のPNGを選ぶ | `current/asset.json` の `poses` にある名前と画像パス |
| 顔アイコンを使う | `current/asset.json` の `icons`（クマは `icons.face`） |
| 動作を組む | `current/clips.json` のフレーム列・時間・効果と、各PNGの登録情報 |
| 全ID・manifestの場所・SHA-256 | `catalogs/asset-library-current-v1.json` の `assets` |
| 原画・生成条件・画風や品質の確認資料 | `asset.json` の元データ参照と[素材ガイド](assets/library/README.md) |

### PNGを1枚取得する

画像だけを使う場合はPythonや動画制作ツールの導入は不要です。[全120種類の素材一覧](assets/library/README.md)から使うPNGを開いて保存できます。Git LFS管理のPNGをURLから取得するときは、画像実体のURLを使ってください。

- [クマの通常PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/bear-beret/current/neutral.png)
- [クマの登録情報JSON](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/bear-beret/current/asset.json)
- [全素材の共通台帳JSON](https://raw.githubusercontent.com/anoneunknowns/youtube/main/catalogs/asset-library-current-v1.json)

画像URLの `bear-beret` を素材一覧のIDへ変えると、各素材の通常PNGを取得できます。再現する版を固定する場合は、PNGとJSONのURLにある `main` を同じコミットSHAへ置き換えます。取得内容が短い `version https://git-lfs.github.com/spec/v1` で始まるテキストなら、画像実体を取得し直してください。取り込み先には選んだ画像と、その出典・利用条件・必要な登録情報を保存します。

### 画像をまとめて取得する

GitとGit LFSを使う例です。最初のcloneではLFS自動取得を止め、画像の共通入口だけを取得します。JSONとガイドはcloneに含まれます。

```sh
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/anoneunknowns/youtube.git num-num-assets
cd num-num-assets
git lfs pull --include="assets/library/characters/*/current/**" --exclude=""
```

PowerShellでの取得、原画・確認資料を含む検証、プレビュー、素材ZIPは[素材ガイド](assets/library/README.md)を参照してください。この取得例は `current/` のPNG用です。元原画まで照合する `character_library.py verify` や `unified_asset_library.py verify` を実行するときは、ガイドの検証用取得範囲を使います。

### JSONから使う画像を解決する

共通台帳の `assets` からIDを選び、`manifest` をリポジトリのルート基準で開きます。manifestのSHA-256は共通台帳の `sha256` と照合できます。その `asset.json` の `neutral` または `poses` から画像を選び、`path` を `asset.json` がある `current/` 基準で解決します。PNGのSHA-256、寸法、`anchor_px`、`reference_height_px` も同じレコードにあります。`source_path` は来歴用のルート相対パスです。

`basic/` は反応・基本動作、`expanded/` は仕草・姿勢、`eyecatch/` は紅茶・おじぎ等の演技、`gimmick/` は背景に配置する素材の動作、`app/` はタップ・回答リアクション・待機・池ジャンプ、`video/` は動画で使う瞬き・挨拶・左右案内・考える／気づく・喜ぶ・固有のしぐさを表す名前空間です。各素材で使える名前は `asset.json` の `poses` を読んでください。互換ローダー `character_library.py` では `basic/` の接頭辞を省き、他は名前空間を付けます。

同じ場面の動作群は `scale = 表示する基準高 / reference_height_px` と登録済み支点で配置します。姿勢ごとの外接高さへ合わせて拡大すると体格が跳ねます。翼・尾・炎・回転翼を含む可視範囲の余白を確保し、各素材の `anchor_kind` と表示上限は[素材ガイド](assets/library/README.md)で確認してください。動作の時間が指定されていないclipは、使う場面で設計・確認します。

クマの通常姿と短い演出18状態も、同じ `current/` から利用できます。原画・登録を選び直す処理はINDEXの `source_collections` と [明示採用の記録](catalogs/character-adoptions-v1.json) を読み、過去の画風QAや最大版数から現行版を推測しません。

反応は `app/blink`・`app/tap_down`・`app/tap_pop`・`app/think`・`app/aha`・`app/success_ready`・`app/success_air`・`app/success_land`・`app/oops`・`app/retry`・`app/cheer`・`app/signature`、待機は `app/idle_rest`・`app/idle_stretch`・`app/idle_nap` から選べます。池の左右姿勢とクマの座位反応は同じ `poses` に登録しています。対象IDでの有無と支点方式は各manifestを読み、[機能別の利用条件](assets/library/README.md#ポーズや動作を使う)に従ってください。

### 公開範囲と記録

GitHubで取得できるファイルは、[公開対象一覧](https://github.com/anoneunknowns/youtube/blob/main/catalogs/github-publication-v1.json)の `files`、原画・登録・確認資料を含む公開素材パッケージの範囲は `character_library_files` が正本です。現行素材と、その採用・利用に必要な入力・資料を公開します。採用中のファイルはフォルダの版番号に関係なく対象です。完成MP4等の動画本体は公開しません。未使用の旧版・不採用候補は新たに追加せず、現在の利用・再制作・必要なQAに使う原本を保管します。容量整理は、明らかに再生成できる大容量動画や用済みの旧build・cacheを優先します。整理の手順は[削除手順](docs/IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合)、実施した削除対象・旧SHA・提供状況は[管理設定](catalogs/character-asset-management-v1.json)の `retirement_records` から確認できます。台帳の履歴パスは配布ファイルの存在を保証しません。

画像・GIF・音声（WAV・MP3等）・フォントはGit LFSで管理します。素材だけを使う際に動画本体・音声モデル・Node.jsは不要です。ファイル整合、過去の採用、現在の画風・動作品質は各確認記録で区別し、取得漏れを隠すためのハッシュ書換えは行いません。利用条件は[素材ガイド](assets/library/README.md)と各依存物の記録を参照してください。

GitHubを更新するときは、[制作原本と公開用checkout](docs/SETUP.md#制作原本とgithub公開用checkout)を区別し、[公開仕様](docs/GITHUB-PUBLICATION.md)で対象選定・隔離検証・限定同期・公開後の取得確認を行います。制作原本にはローカル保管の履歴もあるため、素材ZIPの収録範囲は公開用checkoutと異なります。

## 現行作品

採用先は[作品台帳](catalogs/library-v1.json)の`active_production_set_ids`を正本とします。下表はその現行18作品の入口です。動画の版、音声の版、公開文の版は一致するとは限りません。完成範囲・尺・採用素材・QAと実施範囲は、各制作記録から辿ってください。

| 作品 | 内容・範囲 | 現行制作記録 | 再出力の入口 |
|---|---|---|---|
| 十進数カウント | 1〜300、自然な英語読み | [青空版v002](design/counting-video-v1/blue-sky-production-run-v002.json) | 共通手順：`decimal` |
| 二進数カウント | 0〜1111111₂、桁読み | [v005](design/binary-counting-v1/production-run-v005.json) | 共通手順：`binary` |
| 八進数カウント | 0〜177₈、桁読み | [v002](design/octal-counting-v1/production-run-v002.json) | 共通手順：`octal` |
| 十六進数カウント | 0〜7F₁₆、数字とA〜F | [v002](design/hexadecimal-counting-v1/production-run-v002.json) | 共通手順：`hexadecimal` |
| 4基数同時カウント | 十進0〜200を2・10・8・16進数で表示 | [v002](design/four-base-counting-v1/production-run-v002.json) | 共通手順：`four-base` |
| 偶数カウント | 0〜200を2ずつ、101値 | [v002](design/even-counting-v1/production-run-v002.json) | 共通手順：`even` |
| 奇数カウント | 1〜299を2ずつ、150値 | [v002](design/odd-counting-v1/production-run-v002.json) | 共通手順：`odd` |
| 素数カウント | 1000未満の168素数、2〜997 | [動画v003・公開文改訂v002](design/prime-counting-v1/production-run-v003-publication-v002.json) | 共通手順：`prime` |
| フィボナッチ数列 | F₀=0〜F₄₀=102,334,155、41項 | [v004](design/fibonacci-counting-v1/production-run-v004.json) | 共通手順：`fibonacci` |
| 平方数の数列 | 0²〜100²=10,000、101項 | [v001](design/square-counting-v1/production-run-v001.json) | [専用手順](design/square-counting-v1/production-motion/render-recipe-v002.json) |
| 三角数の数列 | T₀=0〜T₆₀=1,830、61項 | [v002](design/triangular-counting-v1/production-run-v002.json) | [現行ブリーフ](design/triangular-counting-v1/production-brief-v002.txt) |
| コラッツ数列 | 7→1と27→1、129項・127演算 | [v001](design/collatz-counting-v1/production-run-v001.json) | [専用手順](design/collatz-counting-v1/production-v001/reproduction.txt) |
| 2の累乗の数列 | 2⁰〜2⁶⁴、65項 | [v002](design/powers-of-two-counting-v1/production-run-v002.json) | [現行案内](design/powers-of-two-counting-v1/README-production-v002.md) |
| カタラン数の数列 | C₀=1〜C₃₀=3,814,986,502,092,304、31項 | [v004](design/catalan-counting-v1/production-run-v004.json) | [現行案内](design/catalan-counting-v1/PRODUCTION-CURRENT-v004.txt) |
| 等差数列 | 初項2・公差3、2〜302の101項 | [v002](design/arithmetic-sequence-counting-v1/production-run-v002.json) | [公開版の入力・実装](docs/PRODUCTION.md#等差数列の公開版再出力) |
| 等比数列 | 初項2・公比3、41項 | [v002](design/geometric-sequence-counting-v1/production-run-v002.json) | [現行手順](design/geometric-sequence-counting-v1/production-v002/reproduction.txt) |
| トゥエ・モース数列 | 位置0〜255の256項、値は0と1 | [v003](design/thue-morse-counting-v1/production-run-v003.json) | [現行手順](design/thue-morse-counting-v1/README-production-v003.md) |
| リュカ数 | L₀=2・L₁=1〜L₄₀=228,826,127、41項 | [v001](design/lucas-counting-v1/production-run-v001.json) | [現行案内](design/lucas-counting-v1/production-v001/reproduction.txt) |

「共通手順」の9作品は[既存作品の再出力](docs/PRODUCTION.md#既存作品を再出力する)の`portable_production.py`を使い、`--production`へ表の名前を渡します。他の作品は表の専用手順を使います。存在する新しいフォルダや汎用名の旧READMEから、現行版を推定しません。

新作はショート動画以外は原則8分以上です。テンポや読み速度で尺を稼がず、ユーザー指定の例外と過去作品の扱いは[制作仕様](docs/PRODUCTION.md#新作の設計)に従います。公開文は[タイトルと概要の書式](docs/PRODUCTION.md#公開用タイトルと概要の書式)を使い、旧媒体・当時の検査記録を現在の結果へ書き換えません。

## 最初に行うこと

以下は動画を制作・再出力するための手順です。画像だけを利用する場合は [PNGを1枚取得する](#pngを1枚取得する) から始めてください。

1. [セットアップ](docs/SETUP.md) に従い、素材・再現用入力と必要なランタイムを取得する。
2. 再現依存一覧と制作記録に必要なローカル動画を、元のパス・SHAに一致する実体として別途戻す。Git/Git LFSの取得だけでは揃わない。
3. `python tools/verify_workspace.py` で素材・台帳・参照・LFS実体を点検し、`python tools/update_production_archive.py --check` と `python tools/portable_production.py doctor` で再現用入力と環境を確認する。後二者もローカル動画を照合するため、未復元なら不足で停止し得る。
4. `python tools/portable_production.py list` で現行の制作セットを確認する。
5. 静止画プレビューを確認し、新しい出力先へ動画を書き出す。
6. 完成MP4の数値・同期・音声・レイアウトを検査する。

新作を始めるときは [制作手順](docs/PRODUCTION.md#新作の設計) に従い、[制作ブリーフのひな形](templates/production-brief.md) へ作品ごとの設計・担当・検査記録をまとめます。

既存の完成品や採用音声へ上書きせず、新しい出力先を使います。旧 `README.txt` と `PIPELINE.txt` は過去の参照パスを保つ互換案内へ整理しました。手順は本READMEと `docs/`、各版の根拠は作品別の制作記録を参照してください。

## 正本と検査記録

- [ファイル構成と正本](docs/PROJECT-MAP.md)：各仕様の役割、保存対象、ローカル保存と他PC共有の区別。
- [制作仕様](docs/PRODUCTION.md)：設計・音声採用・完成検査・公開文・保存の工程。
- [作品台帳](catalogs/library-v1.json)：現行制作セットと、その制作記録・採用素材・公開文への参照。
- 再現依存一覧（制作原本の参考資料・公開版には未同梱: `reproducibility/production-inputs.json`）：Git/Git LFSから取得する入力と、別途ローカル保管する動画を含む再現依存・SHA。Git取得物だけの一覧ではない。
- [制作ツールの確認記録](docs/TOOLCHAIN.md)：環境・互換性の確認範囲。過去の移植検証（制作原本の参考資料・公開版には未同梱: `reproducibility/validation-20261111/verification.json`）は当時の実施記録。

作品別のQA件数や変更履歴は、上の現行制作記録とそこから参照するレビュー・QAを正本とします。自動解析、抽出画像・動作抜粋の確認、新規ASR/CTC、同一音声の監査継承、人による連続視聴・試聴を区別します。旧版内にある現行の依存原本やQA証拠は、フォルダ名だけで不要と判断しません。

## 利用条件

モデル、フォント、外部ライブラリ等の条件は、各素材の出典と個別の利用条件を確認してください。音声関連は [モデルカード](assets/library/audio/speech/kokoro-af-heart/v002/model-card.md)、[v002のライセンス](assets/library/audio/speech/kokoro-af-heart/v002/licenses/)、[二進数用ライブラリのライセンス](assets/library/audio/speech/kokoro-af-heart/binary-v001/licenses/)、フォントは [M PLUS Rounded 1cのOFL](assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-OFL.txt) から辿れます。

このREADMEは画像・音声・キャラクターへ新しい再配布ライセンスを付与しません。
