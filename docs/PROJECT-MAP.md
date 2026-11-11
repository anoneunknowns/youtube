# ファイル構成と正本

## 入口

| ファイル | 役割 |
|---|---|
| [`README.md`](../README.md) | 現行作品と別PC向けの入口 |
| [`SETUP.md`](SETUP.md) | ランタイム、入力、モデル、環境確認 |
| [`PRODUCTION.md`](PRODUCTION.md) | 再出力、設計、音声採用、最終検査 |
| [`catalogs/library-v1.json`](../catalogs/library-v1.json) | 現行制作セットと採用素材の登録 |
| `reproducibility/production-inputs.json` | Gitへ収納する再現用入力とSHA-256 |
| `reproducibility/archive-policy.json` | 現行作品と依存先を保存する方針 |
| [`README.txt`](../README.txt)、[`PIPELINE.txt`](../PIPELINE.txt) | 元環境のコマンドと各版の制作履歴 |

現行制作セットは `active_production_set_ids`、現行参照画像は `active_reference_set_ids` から辿ります。名前の版数や更新日時だけで採用版を判断しません。

## 再利用する素材

| 場所 | 内容 |
|---|---|
| `assets/library/characters/` | クマ、ウサギ、とら、小鳥等の原画、登録、動作、出典 |
| `assets/library/worlds/` | 庭、オーロラ、天文台、灯台等の背景と構成素材 |
| `assets/library/render-sources/counting-garden/` | 共通の描画素材、フォント、フォントの利用条件 |
| `assets/library/audio/sfx/` | 効果音、生成仕様、権利記録 |
| `assets/library/audio/speech/kokoro-af-heart/` | 採用WAV、実測本文、採用ゲート、発音根拠、モデルと依存ライブラリの利用条件 |
| `assets/library/references/` | 原寸モックアップ、絵コンテ、レイアウト検査、採用素材のhash |
| `assets/library/branding/` | シリーズのバナー・アイコン・サムネイル |

画像を変更するときは、文字や数字を背景に焼き込まず、登録した足元支点と自然高を保ちます。ポーズを変えるためにキャラを別の大きさへ合わせ直しません。

## 設計と制作記録

| 設計フォルダ | 現行の主な資料 |
|---|---|
| `design/counting-video-v1/` | `production-spec-v2.txt`、`cue-sheet-v2.json`、`sound-cue-script-v2.txt`、`blue-sky-production-run-v002.json` |
| `design/binary-counting-v1/` | `production-spec-v005.txt`、`production-review-v005.txt`、`production-run-v005.json` |
| `design/octal-counting-v1/` | 発音調査、台本、`production-run-v002.json` |
| `design/hexadecimal-counting-v1/` | 発音調査、台本、明瞭なAの根拠、`production-run-v002.json` |
| `design/four-base-counting-v1/` | `CURRENT.txt`、`count-to-200-v002/`、`production-run-v002.json`、`production-review-v002.txt` |

`production-run*.json` は、完成品と採用素材・道具・検査記録のSHA-256を束ねます。来歴や検査に絶対パスが残っていても、実行時はリポジトリ内の採用先とマニフェストを使います。古い記録のパス文字列を書き換えるとhashで結ばれた来歴が変わるため、移植だけを理由に書き換えません。

## 動画の再出力に必要な入力

完成MP4だけでは再編集できません。少なくとも採用原画、フォント、実測 `timeline.json`、採用音声WAV、対応する採用・測定記録が必要です。採用 `master.wav` を再利用すれば、音声の再生成・再ミックスを省いて映像を再描画できます。

八進数、十六進数、4基数動画では、作品固有の新しい台詞が元の `output/<作品>/speech/` にあります。元の `output/` は生成物と原本が混在していたため、別PCへ移す際は再現用入力の収納・復元手順に従ってください。フォルダ名だけを見て `speech/` や `timeline.json` を不要なキャッシュとして削除しないでください。

このリポジトリには現行5作品とその制作記録の依存先を収録します。収納対象は `reproducibility/production-inputs.json` に記録し、`tools/update_production_archive.py --check` で確認します。初回の `output/` 保存対象は558ファイル、約1.58GBです。MP4、WAV、PNG、フォント等のバイナリはGit LFSで取得します。Gitへ収納した採用 `output/` 入力と、後で作る任意の `output/<新しい作業>/` を区別してください。

現行作品が旧作品の台詞や比較基準を再利用する場合は、その旧フォルダ内の原本も残します。フォルダ名が旧版でも、依存元であれば保存対象です。不要な旧音声マスター、キャッシュ、診断用生PCMまで一括で収納する構成ではありません。

現行完成品の元の保存先は次のとおりです。

| 作品 | 元の出力フォルダ |
|---|---|
| 十進数 | `output/counting-garden-001-bright-v002/` |
| 二進数 | `output/binary-counting-001-v005-number-gap2s/` |
| 八進数 | `output/octal-counting-001-v002-aligned-reading/` |
| 十六進数 | `output/hexadecimal-counting-001-v002-clear-A/` |
| 4基数 | `output/four-base-counting-001-v002-to-200/` |

各出力には完成MP4、字幕、チャプター、アップロード文、最終QA等があります。4基数動画は `bird-motions.json` も描画に必要です。

## ツールの対応

| 工程 | 主なツール |
|---|---|
| 別PCの環境確認・再出力 | `tools/portable_production.py` |
| 再現用入力の管理 | `tools/update_production_archive.py` |
| 固定モデルの取得・検証 | `tools/portable_models.py` |
| 設計準備 | `video_pipeline.py`、`prepare_*_episode.py`、`build_*_episode.py` |
| 背景・キャラ・数値のモック | `render_*_mockups.py` / `.mjs` |
| 動画描画 | `render_counting_video.py`、`render_binary_video_v003.py`、`render_octal_video.py`、`render_hexadecimal_video.py`、`render_four_base_video_v002.py` |
| 字幕・チャプター・概要 | `export_*_delivery.py`、各 `build_*` のexport |
| 音声合成・採用 | `portable_speech_candidates.mjs`、`verify_speech.mjs`、`portable_verify_phonemes.mjs`、`review_speech_acceptance.mjs` |
| 別PCの採用音声ゲート | `portable_speech_library.py`（原本を保つ派生ゲート） |
| 完成品の検査 | `portable_production.py verify`、`portable_audio.py`、`verify_video*.py`、`verify_*_visual.py`、`verify_*_audio.py`、`verify_*_video.py` |

版付きツールは対応する作品の制作記録に合わせて使います。特に小鳥の200版は `render_four_base_video_v002.py`、`export_four_base_delivery_v002.py`、`verify_four_base_video_v002.py`、`verify_four_base_audio_v002.py` です。

## 管理対象を区別する

- 再利用する原画、台本、採用音声、実測入力、ライセンス、採用根拠、制作記録を保持する。
- `node_modules/`、AIモデルキャッシュ、Pythonキャッシュ、ダウンロード途中、巨大な診断用生PCMは再取得・再生成できる作業データとして扱う。
- `materials/` は持ち込まれた未登録のキャラ参照資料を原本のまま保持する。現行5作品とは独立し、新作へ採用する場合は権利と登録内容を確認してカタログへ追加する。
- 元ゲームの `four-operations` 系リポジトリは別プロジェクト。動画用に登録済みの素材・出典を使い、clone先から元ゲームへ暗黙に依存しない。

Git LFSの対象はルートの `.gitattributes`、追加する原本と除外する作業データの設定は `.gitignore` を確認してください。制作に必要な原本を消して容量を減らす方法は使いません。
