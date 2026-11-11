# Num-Num Numbers — 動画制作プロジェクト

Paspla Studio の数を学ぶ YouTube シリーズについて、企画、英語台本、背景、キャラクター、採用音声、描画・検査ツール、制作記録を管理するリポジトリです。

別PCでの導入は [セットアップ](docs/SETUP.md)、既存作品の再出力と新作の設計は [制作手順](docs/PRODUCTION.md)、正本の位置は [ファイル構成](docs/PROJECT-MAP.md) を参照してください。

画像、WAV、MP4、フォント等はGit LFSで管理します。コードだけでなく採用素材・実測入力・現行の完成品も取得するため、clone後に `git lfs pull` を実行してください。モデルキャッシュと `node_modules/` は保存していません。

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
