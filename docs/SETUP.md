# 別PCでのセットアップ

> この公開版の現行作品と参照先は、同梱のカタログ・公開profileに合わせています。制作原本専用の資料は「公開版には未同梱」と明示します。全履歴用のarchive検査やdoctorには、未同梱の再現依存一覧・原本資料・ローカル動画を別途戻す必要があり、cloneだけで揃うとは扱いません。

## このMacの制作環境（2026年11月11日確認）

このチェックアウトでは `.venv` を有効にすると、Python/Pillowとユーザー領域へ導入したGit・Git LFS・FFmpeg・ffprobeを利用できます。

```sh
cd /Users/support/codex/youtube
source .venv/bin/activate
python --version
git --version
git lfs version
ffmpeg -version
ffprobe -version
```

最新安定版との比較、互換性のため維持した依存、動作確認の範囲は [制作ツールの確認記録](TOOLCHAIN.md) を参照してください。以下のWindows向け手順と過去の制作環境の版数は、再現のための記録として保持しています。

## 制作原本とGitHub公開用checkout

このMacの制作原本は `/Users/support/codex/youtube`、公開用checkoutはその中の `.work/github-current-publication/` です。公開用は制作原本とは別ブランチのGit worktreeで、`.work/` 自体はGitの保存対象外です。作業時には実際のブランチ名とHEADを確認します。

制作原本では現在の利用・再制作・必要なQAに使う原画・入力・媒体を保管し、公開用は必要な非動画を選びます。容量整理は、明らかに再生成できる大容量動画や用済みの旧build・cacheを優先し、判断が曖昧な小さい素材は保持して更新を進めます。旧媒体の一律保管を目的にせず、整理の手順は[画像管理仕様の削除手順](IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合)、当時のパス・SHAと削除済みの提供状況は[管理設定](../catalogs/character-asset-management-v1.json)の `retirement_records` から確認します。制作原本の `main` を公開用へmergeしたり、そのままpushしたりしません。公開profileを制作原本へコピーすることも避け、各checkoutで保存範囲を分けます。ファイル選定、隔離検証、LFS取得、通常pushと公開後の確認は [GitHub公開仕様](GITHUB-PUBLICATION.md) に従います。

以下の番号付き手順は Windows 11 バージョン25H2以降を対象とします。GitHubから取得できる非動画と、別途戻すローカル動画を区別してください。ランタイムはPC共通の場所へ導入し、プロジェクト内へ実行ファイルを複製しません。作業キャッシュと一時ファイルは、DドライブがあればDドライブを優先します。

## 1. リポジトリを取得する

GitとGit LFSをPC共通の場所へ導入してから実行します。採用原画・音声・再現用入力は大容量のため、取得先には複数GBの空き容量を確保してください。完成動画本体は下記のローカル保管と区別します。再描画では別途、一時画像と音声・動画の書出し領域も使います。

```powershell
git lfs install
git clone https://github.com/anoneunknowns/youtube.git
Set-Location youtube
git lfs pull
git lfs fsck
```

以後のコマンドはリポジトリ直下で実行します。clone先は元PCと同じ `D:\codex_projects\youtube` である必要はありません。

Git/Git LFSから取得するのは、保存対象として登録された画像・採用WAV/MP3・フォント・台本・実測JSON・コード・制作記録と依存原本です。LFSポインタだけでは画像やWAVを開けないため、`git lfs pull`の終了と実体を確認します。`output/`にも採用台詞・実測タイムライン・音声マスター等の原本がありますが、任意の一時出力まで全てをGitへ追加する必要はありません。

素材の取得確認だけなら、公開profileに対応する `python tools/verify_github_publication.py --check-git` と素材の検査を使います。履歴を含む制作原本の再現依存一覧と、公開版の収録範囲は同じではありません。全体の再現検査は、後述の不足するローカル動画等を戻してから実行します。

MP4・MOV・MKV・WebM等の動画ファイルはpush対象外のローカル保管です。この版のcloneと`git lfs pull`で完成動画を取得できるとは扱いません。`.gitattributes`に残る`*.mp4 filter=lfs`は履歴上の属性であり、現在の動画がGitで追跡・pushされていることや取得できることを保証しません。画像・GIF・MP3等の音声はこの動画除外の対象ではありません。

台帳・制作記録の動画パスとSHAは当時の証拠として維持します。動画本体が必要な検査は、ローカル保管の完成品を戻すか、採用入力から未使用の出力先へ再描画して、その新しい動画を対象に実行します。別環境の再描画で旧MP4と同じSHAになる保証はありません。元動画が存在しないことを理由に旧QAの対象SHAを書き換えません。原本と作業データの区分は[ファイル構成](PROJECT-MAP.md#管理対象を区別する)を参照してください。

Pythonの準備後、再現依存のマニフェストも確認します。次の`--check`と後段の`portable_production.py doctor`は、ローカル動画もパス・SHAで照合します。一覧と制作記録に必要な動画を、元のパス・SHAに一致する実体として別途戻してから実行してください。Gitだけのclone後には不足で停止し得ます。

```powershell
python tools/update_production_archive.py --check
```

Git/Git LFSから取得する入力と、別途ローカル保管する動画を含む再現依存・SHA-256・ファイル数・容量は再現依存一覧（制作原本の参考資料・公開版には未同梱: `reproducibility/production-inputs.json`）、保存範囲の方針は[保管方針](../reproducibility/archive-policy.json)が管理します。この一覧はGit取得物だけの一覧ではありません。依存する原画・原音・採用ゲート・動作登録・QA根拠は旧版内にある場合も含まれます。

現行の採用先と作品別再出力の入口は[READMEの現行作品一覧](../README.md#現行作品)から選びます。共通CLIに対応する9作品と、専用手順を使う作品を区別してください。実測音声base、映像上の親版、動作、公開文の保存先は各制作記録に従い、版番号の大小だけで選びません。新作の8分原則・テンポ・例外は[制作仕様](PRODUCTION.md#新作の設計)を参照します。

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

同梱の `.npmrc` は、インストール処理が必要な `onnxruntime-node@1.21.0` と `protobufjs@7.6.6` の2固定版だけを許可します。`sharp@0.35.5` にはインストールスクリプトがないため許可一覧へ追加しません。`package.json` の `overrides.sharp` とロックは、セキュリティ修正版を固定する組です。この設定を保持し、リポジトリ直下でそのまま `npm ci` を実行します。一括の `approve --all` や手元での `package.json` の変更は不要です。更新理由と確認範囲は [制作ツールの記録](TOOLCHAIN.md#2026年11月14日の画像処理依存の修正)、許可設定の詳細は [npm公式のinstall scripts説明](https://docs.npmjs.com/cli/commands/npm-install-scripts/) を参照してください。

## 3. 一時フォルダと実行環境を確認する

手順1で必要なローカル動画も復元してから実行します。

```powershell
$workRoot = if (Test-Path 'D:\') {
    'D:\temp\num-num-numbers'
} else {
    Join-Path ([IO.Path]::GetTempPath()) 'num-num-numbers'
}
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null
python tools/verify_workspace.py
python tools/portable_production.py doctor --work-dir $workRoot
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
| MP4等の動画がclone先にない | 動画はローカル保管。元動画が必要な検査か、新しく再描画した動画を検査する工程かを確認する |
| hash不一致で停止する | 誤って原本を編集していないか、未完了の取得や別版が混在していないか |
| 元PCのパスへアクセスする | 移植用入口を使っているか。履歴の個別ツールを直接実行していないか |
| 既存出力への上書きを拒否される | 新しい出力フォルダ名を指定する |

hash検査を無効にして進めず、現在の採用版・原本・再現用入力を照合してください。
