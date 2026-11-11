# 別PCでのセットアップ

この手順は Windows 11 バージョン25H2以降を対象とします。ランタイムはPC共通の場所へ導入し、プロジェクト内へ実行ファイルを複製しません。作業キャッシュと一時ファイルは、DドライブがあればDドライブを優先します。

## 1. リポジトリを取得する

GitとGit LFSをPC共通の場所へ導入してから実行します。原画・音声・完成動画は大容量のため、取得先には複数GBの空き容量を確保してください。再描画では別途、一時画像と音声・動画の書出し領域も使います。

```powershell
git lfs install
git clone https://github.com/anoneunknowns/youtube.git
Set-Location youtube
git lfs pull
git lfs fsck
```

以後のコマンドはリポジトリ直下で実行します。clone先は元PCと同じ `D:\codex_projects\youtube` である必要はありません。

Git LFSのポインタだけ取得した状態では、画像・WAV・MP4を開けません。`git lfs pull` が正常に終了し、実ファイルが揃っていることを確認します。現行7作品の再現に必要な `output/` 内の採用台詞、実測タイムライン、音声マスターと、それらの依存原本も管理対象です。任意の一時出力まで全てをGitへ追加する必要はありません。

奇数の採用先は1〜299の150値を数えるv002（8分55.80秒・16074フレーム）です。`output/odd-counting-001-v002/` のタイムラインとマスター、依存するv001の採用音声・検査根拠を取得してください。新作の尺は [制作手順](PRODUCTION.md) の「ショート動画以外は原則1本8分以上」に従い、通常2秒の間隔を保って範囲で調整します。

Pythonの準備後、再現用入力のマニフェストも確認します。

```powershell
python tools/update_production_archive.py --check
```

収納対象とSHA-256は `reproducibility/production-inputs.json`、収納範囲の方針は `reproducibility/archive-policy.json` が管理します。初回整理では `output/` の必要な558ファイル、計約1.58GBを保存しています。これに共通素材や設計資料が加わります。

## 2. ランタイムを用意する

下表は2026年11月11日の制作・検査で使用した版です。「常に最新版を使う」という要件ではなく、再現時の基準です。別の版を使う場合は完成ファイルの検査を改めて実施してください。

| 実行環境 | 制作で使用した版 | 主な用途 |
|---|---|---|
| PowerShell | 7.6.9 | Windowsでの準備・操作 |
| Git | インストール済みの共通Git | clone、変更管理 |
| Python | 3.15.2 | 計画、画像描画、ミックス、動画検査 |
| Pillow | 13.0.0 | PNG、フォント、レイアウト描画 |
| FFmpeg / ffprobe | 9.0.2 | 音声処理、H.264/AAC書出し、全編検査 |
| Node.js | 26.13.0 | 新規音声生成、ASR・音素検査 |
| npm | 12.2.1 | lock済みのJavaScript依存を導入 |
| kokoro-js | 1.2.1 | ローカル英語TTS |
| @huggingface/transformers | 3.8.1 | TTS、音声認識、CTC音素認識 |

FFmpegは `libx264` とAACエンコーダーを含む配布を使用します。`ffmpeg` と `ffprobe` をOSのPATHへ登録するか、移植用ツールの `--ffmpeg` / `--ffprobe` に実行ファイルの絶対パスを渡します。

```powershell
python --version
node --version
npm --version
ffmpeg -version
ffprobe -version
python -m pip install -r requirements.txt
```

既存の採用済み音声とマスターを使うプレビュー・再描画では、Node.jsやAIモデルのダウンロードは不要です。新しい音声を生成する場合、またはASR・CTC検査を再実行する場合は次も実行します。

```powershell
npm ci
```

`npm install` による依存更新ではなく、採用済みの `package-lock.json` を使います。Python側の必須外部依存はPillowです。

npm 12.2.1で必要な依存インストール処理は、同梱の `.npmrc` で `onnxruntime-node@1.21.0`、`protobufjs@7.6.6`、`sharp@0.34.5` の3つの固定版だけを許可しています。この設定を保持し、リポジトリ直下でそのまま `npm ci` を実行します。一括の `approve --all` や `package.json` の変更は不要です。設定の詳細は [npm公式のinstall scripts説明](https://docs.npmjs.com/cli/commands/npm-install-scripts/) を参照してください。

## 3. 一時フォルダと実行環境を確認する

```powershell
$workRoot = if (Test-Path 'D:\') {
    'D:\temp\num-num-numbers'
} else {
    Join-Path ([IO.Path]::GetTempPath()) 'num-num-numbers'
}
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
python tools/portable_production.py doctor
python tools/portable_production.py list
```

元PCの `C:\Python315`、`D:\dev`、ユーザー名、ゲーム側の別リポジトリは、別PCの実行先としてコピーしません。履歴のJSON・ログに記録された絶対パスは、その時点の来歴として残しています。

## 4. 最初は静止画を作る

```powershell
python tools/portable_production.py preview --production four-base --out-dir output/four-base-preview-new --work-dir $workRoot
```

プレビューで小鳥、背景、全ての行、タイトル、最大桁数を確認してから、[制作手順](PRODUCTION.md) の `render` と `verify` を実行します。出力先は存在しない新しいフォルダ名にします。

## 5. 新しい音声や独立ASRを使う場合

採用済みWAVを再利用するだけならモデルは不要です。新しい本文や別の声を作る場合は、元WAVを上書きせず候補として生成し、語認識・音素・語末を確認してから採用します。

| 用途 | ローカルモデル | 固定・確認する資料 |
|---|---|---|
| 英語TTS | `onnx-community/Kokoro-82M-v1.0-ONNX`、`af_heart`、fp32、速度0.98 | `assets/library/audio/speech/kokoro-af-heart/v002/model-files.json`、`voice-profile.json` |
| 語認識 | `Xenova/whisper-tiny.en`、q8 | `tools/verify_speech.mjs` のrevisionとONNXのSHA-256 |
| 独立音素認識 | `onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX`、q8 | `tools/verify_phonemes.mjs` と既存の音素検査資料 |

移植用のモデル準備ツールでは、キャッシュ先を指定して固定revisionのファイルを取得・検証できます。

```powershell
$modelCache = if (Test-Path 'D:\') {
    'D:\dev\caches\huggingface'
} else {
    Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'num-num-numbers\model-cache'
}
python tools/portable_models.py --model all --cache-root $modelCache
```

必要なモデルだけを準備する場合は `--model all` の代わりに `--model kokoro`、`--model asr`、`--model phoneme` を指定します。すでに取得済みのモデルを通信せず検査する場合は `--check-only` を付けます。このツールはサイズとSHA-256を検証します。モデル本体、`node_modules/`、ダウンロード途中のファイルはGitへ収納する制作原本と区別します。

新規候補の生成は `portable_speech_candidates.mjs`、音素認識は `portable_verify_phonemes.mjs` を入口にします。どちらも任意のモデルキャッシュを指定でき、音素検査のFFmpegも明示できます。具体例は [制作手順](PRODUCTION.md) を参照してください。

旧 `prepare_phoneme_model.ps1` と一部の個別検査ツールには元PCのパスが残っています。別PCでは移植用の入口を使用します。既存音声の採用記録だけを再利用する工程と、新しい認識結果を得る工程を混同しないでください。

## うまく動かない場合

| 症状 | 確認すること |
|---|---|
| `PIL` が見つからない | 実行している `python` と、Pillowを入れたPythonが同じか |
| FFmpegが見つからない | `ffmpeg` / `ffprobe` のPATHまたは明示パス |
| 入力WAVやtimelineが見つからない | 再現に必要な入力ファイルを取得済みか。完成動画だけでは再描画できない |
| hash不一致で停止する | 誤って原本を編集していないか、未完了の取得や別版が混在していないか |
| 元PCのパスへアクセスする | 移植用入口を使っているか。履歴の個別ツールを直接実行していないか |
| 既存出力への上書きを拒否される | 新しい出力フォルダ名を指定する |

hash検査を無効にして進めず、現在の採用版・原本・再現用入力を照合してください。
