# Num-Num Numbers — 動画制作プロジェクト

Paspla Studio の数を学ぶ YouTube シリーズについて、企画、英語台本、背景、キャラクター、採用音声、描画・検査ツール、制作記録を管理するリポジトリです。

別PCでの導入は [セットアップ](docs/SETUP.md)、既存作品の再出力と新作の設計は [制作手順](docs/PRODUCTION.md)、正本の位置は [ファイル構成](docs/PROJECT-MAP.md) を参照してください。

キャラクターの採用原画・基本動作を他のAIや別PCで利用する場合は、[素材の利用案内](assets/library/README.md)と[機械可読台帳](catalogs/character-library-v1.json)を起点にしてください。検証・プレビュー・保管用ZIPの作成は `python tools/character_library.py` で行えます。

画像、WAV、MP4、フォント等はGit LFSで管理します。コードだけでなく採用素材・実測入力・現行の完成品も取得するため、clone後に `git lfs pull` を実行してください。モデルキャッシュと `node_modules/` は保存していません。

## 他プロジェクトのAI向け：キャラクター素材の場所と利用方法

このリポジトリは、動画制作に加えて共通キャラクター素材の保管先です。別のプロジェクトへ取り込むAIは、まず[利用案内](assets/library/README.md)と[素材を扱うAIへの指示](assets/library/AGENTS.md)を読み、[採用版台帳](catalogs/character-library-v1.json)の明示されたパスから素材を選んでください。

| 探すもの | 保存場所・入口 |
|---|---|
| 採用する画像・ポーズ・SHA-256・描画座標 | [`catalogs/character-library-v1.json`](catalogs/character-library-v1.json) |
| キャラクターの原画・動作PNG | [`assets/library/characters/`](assets/library/characters/) |
| 新7種類の通常姿一覧・採用版記録 | [`assets/library/collections/animal-stock/v001/`](assets/library/collections/animal-stock/v001/) |
| 新7種類・42ポーズの一覧・動作プレビュー | [`assets/library/collections/animal-motions/v001/`](assets/library/collections/animal-motions/v001/) |
| 全保管ファイルのサイズ・ハッシュ | [`catalogs/character-library-files-v1.json`](catalogs/character-library-files-v1.json) |
| 一覧・検証・プレビュー・素材専用ZIPの作成 | [`tools/character_library.py`](tools/character_library.py) |

既存のクマ・ウサギ・とら・小鳥を含む11種類の通常姿を参照できます。新しいシャム猫、レッサーパンダ、ミーアキャット、カンガルー、ハリネズミ、ヤイロチョウ、オナガドリには、それぞれ通常姿と6種類の表情・動作PNGを保存しています。既存4種類の従来の動作は専用の登録・描画処理を使います。

新7種類の通常姿は `assets/library/characters/<ID>/sources/<採用版>/neutral.png`、動作PNGと足支点は同じキャラクターの `motions/v001/` にあります。例えばレッサーパンダの通常姿は [`assets/library/characters/red-panda/sources/v001/neutral.png`](assets/library/characters/red-panda/sources/v001/neutral.png)、動作登録は [`assets/library/characters/red-panda/motions/v001/registration.json`](assets/library/characters/red-panda/motions/v001/registration.json) です。調整前の画像も保存しているため、最大のバージョン番号や更新日時から採用版を推測せず、台帳の指定を使ってください。



| 新キャラクター | ID | 採用する通常姿PNG |
|---|---|---|
| シャム猫 | `siamese-cat` | [`sources/v005/neutral.png`](assets/library/characters/siamese-cat/sources/v005/neutral.png) |
| レッサーパンダ | `red-panda` | [`sources/v001/neutral.png`](assets/library/characters/red-panda/sources/v001/neutral.png) |
| ミーアキャット | `meerkat` | [`sources/v004/neutral.png`](assets/library/characters/meerkat/sources/v004/neutral.png) |
| カンガルー | `kangaroo` | [`sources/v002/neutral.png`](assets/library/characters/kangaroo/sources/v002/neutral.png) |
| ハリネズミ | `hedgehog` | [`sources/v003/neutral.png`](assets/library/characters/hedgehog/sources/v003/neutral.png) |
| ヤイロチョウ | `fairy-pitta` | [`sources/v001/neutral.png`](assets/library/characters/fairy-pitta/sources/v001/neutral.png) |
| オナガドリ | `onagadori` | [`sources/v002/neutral.png`](assets/library/characters/onagadori/sources/v002/neutral.png) |

動作PNGは上の各IDの `assets/library/characters/<ID>/motions/v001/<pose>.png` にあります。例えば `red-panda/motions/v001/greet.png` が挨拶ポーズです。既存4種類のIDは `bear-beret`、`rabbit-beret`、`tora`、`little-bird` です。

画像・GIFはGit LFSで管理しています。素材だけを取得する場合は、初回clone時のLFS自動取得を止めたうえで、`assets/library/characters/**` と `assets/library/collections/animal-stock/**` と `assets/library/collections/animal-motions/**` を対象に `git lfs pull` を実行します。画像本体を取得後、リポジトリのルートから次を実行してください。

```powershell
git lfs pull --include="assets/library/characters/**,assets/library/collections/animal-stock/**,assets/library/collections/animal-motions/**" --exclude=""
python -m pip install -r requirements.txt
python tools/character_library.py list --json
python tools/character_library.py verify
python tools/character_library.py preview --character red-panda --pose cheer --height 430 --output D:/temp/red-panda-cheer.png
python tools/character_library.py export --output D:/temp/num-num-character-library.zip
```

出力先は取り込み先の環境に合わせて変更してください。`export` のZIPは、11種類の通常姿、新7種類の動作、台帳、生成条件、検証記録、ツール、依存指定をまとめた素材専用パッケージです。取り込み時は画像だけを抜き出さず、台帳・登録情報と相対配置を一緒に維持してください。動画本体や音声モデルのキャッシュは不要です。

台帳の `path_base` は `library-root` です。通常姿の `image_region_px`・`anchor_px`・`reference_height_px`、動作の `key_poses.poses`・`common_reference_height_px` を使って描画します。ウサギの通常姿はシート内の指定領域であり、単独PNGとしてシート全体を使わないでください。同じ動物の動作には共通の縮尺と足支点を使い、屈伸やついばみ姿勢を個別の画像高さで拡大しません。オナガドリは身体で縮尺を決め、長い尾の領域を別に確保します。

`generation-prompt.txt`・`generation-input.json`・`source-manifest.json`・`registration.json` と各collectionの `qa-evidence/` は、派生素材を作る際の根拠です。過去の生成先 `C:/...` や `D:/temp/...` は履歴であり、現在のPCに存在する前提にしません。採用原画を上書きせず、修正版は新しい版として保存します。キーポーズの補間・音声同期・余白は実際の取り込み先の画面で確認してください。利用条件は各素材・依存物の既存記録を確認し、この説明から新たな利用許諾を推定しないでください。

## 現行の5作品

現行版の判定は [`catalogs/library-v1.json`](catalogs/library-v1.json) の `active_production_set_ids` を使います。素材の `v001` が旧素材を意味するとは限りません。

| 作品 | 範囲・音声 | キャラクターと背景 | 完成尺 | 制作記録 |
|---|---|---|---|---|
| 十進数カウント | 1〜300、十進数の自然な英語読み | 赤い帽子のクマ・青空の庭 | 8分16.97秒 | [青空版v002](design/counting-video-v1/blue-sky-production-run-v002.json) |
| 二進数カウント | 0〜1111111₂、各桁を英語で読む | 同じクマ・夕暮れの庭・十進数看板 | 21分31.10秒 | [v005](design/binary-counting-v1/production-run-v005.json) |
| 八進数カウント | 0〜177₈、各桁を英語で読む | ピンクのウサギ・オーロラの庭 | 10分42.97秒 | [配置修正版v002](design/octal-counting-v1/production-run-v002.json) |
| 十六進数カウント | 0〜7F₁₆、数字とA〜Fを読む | とら・星空の天文台 | 9分22.73秒 | [明瞭なAへ改訂したv002](design/hexadecimal-counting-v1/production-run-v002.json) |
| 4基数同時カウント | 十進0〜200を2・10・8・16進数で表示、音声は十進数 | 小鳥・海辺の灯台 | 11分02.37秒 | [200までのv002](design/four-base-counting-v1/production-run-v002.json) |

直近の小鳥動画は全201値・804表記、通常の数の読み終わりから次の読み始めまで197か所を2秒、説明を挟む3か所を5秒にしています。桁読み動画の「桁間0.9秒」を、自然な十進数の語の間へ挿入しないでください。

## 最初に行うこと

1. [セットアップ](docs/SETUP.md) に従い、素材・再現用入力と必要なランタイムを取得する。
2. `python tools/update_production_archive.py --check` で取得した再現用入力を検査し、`python tools/portable_production.py doctor` で環境を確認する。
3. `python tools/portable_production.py list` で現行の制作セットを確認する。
4. 静止画プレビューを確認し、新しい出力先へ動画を書き出す。
5. 完成MP4の数値・同期・音声・レイアウトを検査する。

既存の完成品や採用音声へ上書きせず、新しい出力先を使います。旧 [`README.txt`](README.txt) と [`PIPELINE.txt`](PIPELINE.txt) は過去の制作環境と各版の履歴を含むため、別PCでは本READMEと `docs/` の手順を入口にしてください。

## 正本と検査記録

- [`catalogs/library-v1.json`](catalogs/library-v1.json)：現行作品と採用素材の登録。
- [`design/`](design/)：脚本、発音調査、制作仕様、絵コンテ、制作記録。
- [`assets/library/`](assets/library/)：再利用する原画、背景、動作、フォント、効果音、検査済み音声と利用条件。
- [`tools/`](tools/)：設計準備、音声合成・検査、動画描画、字幕出力、最終検査。
- [`tests/`](tests/)：時刻計算、音声採用ゲート、配置等の回帰検査。

直近の小鳥動画は [制作記録](design/four-base-counting-v1/production-run-v002.json) と [独立再検査](design/four-base-counting-v1/production-qa/v002-recheck-20261111/verification.json) を参照してください。検査は自動解析と抽出画像の確認を含み、全編の人による試聴・視聴を行ったという記録ではありません。

移植手順は同じWindows上の別のGit/LFSチェックアウトで検証しました。137件のテスト、全5作品のプレビュー、新しい音声の生成・ASR・CTC、旧パスを持つ採用音声の参照解決を確認しています。[検証記録](reproducibility/validation-20261111/verification.json) に実施範囲と根拠を保存しています。

## 利用条件

モデル、フォント、外部ライブラリ等の条件は、各素材の出典・モデルカード・`licenses/` を確認してください。このREADMEは画像・音声・キャラクターへ新しい再配布ライセンスを付与しません。
