# ファイル構成と正本

> この公開版の現行作品と参照先は、同梱のカタログ・公開profileに合わせています。制作原本専用の資料は「公開版には未同梱」と明示します。全履歴用のarchive検査やdoctorには、未同梱の再現依存一覧・原本資料・ローカル動画を別途戻す必要があり、cloneだけで揃うとは扱いません。

## 入口

| ファイル | 役割 |
|---|---|
| [`README.md`](../README.md) | 現行作品と別PC向けの入口 |
| [`SETUP.md`](SETUP.md) | ランタイム、入力、モデル、環境確認 |
| [`GITHUB-PUBLICATION.md`](GITHUB-PUBLICATION.md) | 制作原本と公開用worktreeの分離、非動画の選定・同期・LFS取得・公開後の確認 |
| [`TOOLCHAIN.md`](TOOLCHAIN.md) | 制作ツールの確認履歴、互換性と環境の使い分け |
| [`PRODUCTION.md`](PRODUCTION.md) | 出力標準、設計・再出力・音声採用・完成検査の実施工程 |
| [`IMAGE-ASSET-MANAGEMENT.md`](IMAGE-ASSET-MANAGEMENT.md) | 画像の担当・来歴・採用管理と、画風・精細さ・素材登録の受入条件 |
| [`LAYOUT-ALIGNMENT.md`](LAYOUT-ALIGNMENT.md) | 枠内の配置意図、実描画の測定、軸別許容差、配置QAの記録条件 |
| [`templates/production-brief.md`](../templates/production-brief.md) | 作品別の設計・担当・進捗・QA根拠・再開点を記入するひな形。共通条件は各正本を参照 |
| [`catalogs/character-asset-management-v1.json`](../catalogs/character-asset-management-v1.json)、[`character-asset-registry-v1.json`](../catalogs/character-asset-registry-v1.json) | 全キャラクター生成バッチの分類・担当・確定在庫と生成中の保留 |
| [`catalogs/library-v1.json`](../catalogs/library-v1.json) | 現行制作セットと採用素材の登録 |
| reproducibility/production-inputs.json（制作原本の参考資料・公開版には未同梱: `reproducibility/production-inputs.json`） | ローカル動画を含む再現依存の照合一覧とSHA-256。Git共有対象の一覧とは別 |
| `reproducibility/archive-policy.json` | 現行作品と依存先を保存する方針 |
| [`materials/README.md`](../materials/README.md)、[`materials/manifest-v1.json`](../materials/manifest-v1.json) | 未登録の持込資料と原本の目録 |
| reproducibility/organization-20261112-v001/manifest.json（制作原本の参考資料・公開版には未同梱: `reproducibility/organization-20261112-v001/manifest.json`） | 整理対象・判断・実施結果・保存点と確認範囲の記録 |
| [`README.txt`](../README.txt)、[`PIPELINE.txt`](../PIPELINE.txt) | 過去の参照パスを保つ短い互換案内。手順本文は本表のMarkdown仕様へ統合 |

現行制作セットは `active_production_set_ids`、現行参照画像は `active_reference_set_ids` から辿ります。名前の版数や更新日時だけで採用版を判断しません。

共通の画像素材は `catalogs/asset-library-current-v1.json` と各素材の `current/asset.json` が入口です。通常姿・汎用ポーズの明示採用は `catalogs/character-adoptions-v1.json` とINDEXで管理し、作品が採用した固定入力とは分けます。素材の更新だけで現行作品の採用版や過去の検査結果を変更しません。

受入条件は担当する仕様を正本とし、制作工程やAI向け指示には実行時の要点と参照先を記載します。画像管理・配置の仕様は素材専用ZIPにも同梱し、素材単独で必要な条件を読める状態を保ちます。

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

現行18作品の設計・採用記録と再出力先を一表にまとめます。台本、モック、素材登録、各QAの詳細は制作記録から辿ります。採用先を変更するときは、表だけでなく作品台帳の現行IDと対応する入口を合わせて更新します。

| 作品 | 設計・現行採用記録 | 再出力の入口 | 完成品のローカル保管先 |
|---|---|---|---|
| 十進数 | [設計](../design/counting-video-v1/)・[採用記録](../design/counting-video-v1/blue-sky-production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `decimal` | `output/counting-garden-001-bright-v002/` |
| 二進数 | [設計](../design/binary-counting-v1/)・[採用記録](../design/binary-counting-v1/production-run-v005.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `binary` | `output/binary-counting-001-v005-number-gap2s/` |
| 八進数 | [設計](../design/octal-counting-v1/)・[採用記録](../design/octal-counting-v1/production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `octal` | `output/octal-counting-001-v002-aligned-reading/` |
| 十六進数 | [設計](../design/hexadecimal-counting-v1/)・[採用記録](../design/hexadecimal-counting-v1/production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `hexadecimal` | `output/hexadecimal-counting-001-v002-clear-A/` |
| 4基数 | [設計](../design/four-base-counting-v1/)・[採用記録](../design/four-base-counting-v1/production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `four-base` | `output/four-base-counting-001-v002-to-200/` |
| 偶数 | [設計](../design/even-counting-v1/)・[採用記録](../design/even-counting-v1/production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `even` | `output/even-counting-001-v002/` |
| 奇数 | [設計](../design/odd-counting-v1/)・[採用記録](../design/odd-counting-v1/production-run-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `odd` | `output/odd-counting-001-v002/` |
| 素数 | [設計](../design/prime-counting-v1/)・[採用記録](../design/prime-counting-v1/production-run-v003-publication-v002.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `prime` | `output/prime-counting-001-v003/` |
| フィボナッチ | [設計](../design/fibonacci-counting-v1/)・[採用記録](../design/fibonacci-counting-v1/production-run-v004.json) | [共通CLI](PRODUCTION.md#既存作品を再出力する) `fibonacci` | `output/fibonacci-counting-001-v004/production-v002/` |
| 平方数 | [設計](../design/square-counting-v1/)・[採用記録](../design/square-counting-v1/production-run-v001.json) | [専用手順](../design/square-counting-v1/production-motion/render-recipe-v002.json) | `output/square-counting-001-v001/production-v004/` |
| 三角数 | [設計](../design/triangular-counting-v1/)・[採用記録](../design/triangular-counting-v1/production-run-v002.json) | [専用手順](../design/triangular-counting-v1/production-brief-v002.txt) | `output/triangular-counting-001-v002/` |
| コラッツ | [設計](../design/collatz-counting-v1/)・[採用記録](../design/collatz-counting-v1/production-run-v001.json) | [専用手順](../design/collatz-counting-v1/production-v001/reproduction.txt) | `output/collatz-counting-001-v001/delivery-v001/` |
| 2の累乗 | [設計](../design/powers-of-two-counting-v1/)・[採用記録](../design/powers-of-two-counting-v1/production-run-v002.json) | [専用手順](../design/powers-of-two-counting-v1/README-production-v002.md) | `output/powers-of-two-counting-001-v001/video/v004-audio-reencoded/` |
| カタラン数 | [設計](../design/catalan-counting-v1/)・[採用記録](../design/catalan-counting-v1/production-run-v004.json) | [専用手順](../design/catalan-counting-v1/PRODUCTION-CURRENT-v004.txt) | `output/catalan-counting-001-v007/` |
| 等差数列 | [設計](../design/arithmetic-sequence-counting-v1/)・[v002](../design/arithmetic-sequence-counting-v1/production-run-v002.json) | [公開版の入力・実装](PRODUCTION.md#等差数列の公開版再出力) | `output/arithmetic-sequence-counting-001-v001/render/v004/` |
| 等比数列 | [設計](../design/geometric-sequence-counting-v1/)・[採用記録](../design/geometric-sequence-counting-v1/production-run-v002.json) | [専用手順](../design/geometric-sequence-counting-v1/production-v002/reproduction.txt) | `output/geometric-sequence-counting-001-v002/delivery-v001/` |
| トゥエ・モース | [設計](../design/thue-morse-counting-v1/)・[採用記録](../design/thue-morse-counting-v1/production-run-v003.json) | [専用手順](../design/thue-morse-counting-v1/README-production-v003.md) | `output/thue-morse-counting-001-v003/delivery-v001/` |
| リュカ数 | [設計](../design/lucas-counting-v1/)・[採用記録](../design/lucas-counting-v1/production-run-v001.json) | [専用手順](../design/lucas-counting-v1/production-v001/reproduction.txt) | `output/lucas-counting-001-v001/render/full-v002/` |

`production-run*.json` は、完成品と採用素材・道具・検査記録のSHA-256を束ねます。公開文だけの改訂と媒体の改訂を区別し、最大の版番号や汎用名のREADMEだけで現行を判断しません。来歴に絶対パスが残っていても、実行時は登録されたリポジトリ内の採用先を使います。移植のために過去の記録を書き換えると、ハッシュで結ばれた来歴が変わるため、そのまま保全します。

## 動画の再出力に必要な入力

完成MP4だけでは再編集できません。採用原画・登録尺度と支点、フォントと利用条件、実測 `timeline.json`、採用原音とゲート、音声マスター、動作情報、描画コードと設定を、上表の現行制作記録に合わせて使います。合格AACをcopyする作品では、そのAACと受入記録も必要です。音声を再利用する再描画と、原音からの再ビルドを区別します。

`output/` には完成品と原本が混在します。固有の台詞を保存した `speech/`、実測 `audio-build/`、旧版にあるタイムライン・音源・比較基準も、現行の依存先であれば保全します。例えばフィボナッチの現行映像・動作はv004ですが、採用原音・PCM・AACはv002の固定入力を参照します。必要な版別パスは制作記録を使い、フォルダ名の古さだけで削除しません。

再現依存一覧（制作原本の参考資料・公開版には未同梱: `reproducibility/production-inputs.json`） の `files`・`totals` は、ローカル動画も含む保存・照合対象です。Gitで共有する画像・音声・JSON・フォント等は、追跡設定に従ってGit/LFSから取得します。完成MP4等の動画は現在push対象外で、別途保管・移送します。`.gitattributes` に残るMP4向けLFS属性は、動画の追跡・push・取得を保証しません。

GitのみのcloneとLFS取得では、一覧の動画依存が揃わない場合があります。必要な保存動画を**元のパスとSHA-256に合わせて復元してから**、`python tools/update_production_archive.py --check` と `python tools/portable_production.py doctor` を実行します。再描画は環境差で旧MP4と同じSHAにならないことがあるため、旧QAや期待SHAを書き換えて復元の代用にしません。詳しい移送手順は [セットアップ](SETUP.md) を使います。

## ツールの対応

| 工程 | 主なツール |
|---|---|
| 別PCの環境確認・再出力 | `tools/portable_production.py` |
| 素材・台帳・ID・QA参照・LFS実体の全体検査 | `tools/verify_workspace.py` |
| 再現用入力の管理 | `tools/update_production_archive.py` |
| 採用素材の一覧・参照・素材専用ZIP | `tools/character_library.py` |
| 全素材の共通currentビュー・master | `tools/unified_asset_library.py` |
| 公開profileと実体・Git indexの照合 | 公開用checkoutの `tools/verify_github_publication.py`。制作原本の全履歴検査とは対象を分ける |
| 固定モデルの取得・検証 | `tools/portable_models.py` |
| 設計準備 | `video_pipeline.py`、`prepare_*_episode.py`、`build_*_episode.py` |
| 背景・キャラ・数値のモック | `render_*_mockups.py` / `.mjs` |
| 動画描画 | 共通CLI、または採用記録・専用手順に指定した `render_*_video*.py` 等。現行版と履歴版を取り違えない |
| 字幕・チャプター・概要 | `export_*_delivery.py`、各 `build_*` のexport |
| 音声合成・採用 | `portable_speech_candidates.mjs`、`verify_speech.mjs`、`portable_verify_phonemes.mjs`、`review_speech_acceptance.mjs` |
| 別PCの採用音声ゲート | `portable_speech_library.py`（原本を保つ派生ゲート） |
| 完成品の検査 | `portable_production.py verify`、`portable_audio.py`、`verify_video*.py`、`verify_*_visual.py`、`verify_*_audio.py`、`verify_*_video.py` |

版付きツールは対応する作品の制作記録に合わせて使います。特に小鳥の200版は `render_four_base_video_v002.py`、`export_four_base_delivery_v002.py`、`verify_four_base_video_v002.py`、`verify_four_base_audio_v002.py` です。

## 管理対象を区別する

保存・整理の単位はフォルダ名ではなく、担当・用途・採用範囲・参照関係です。`output/`、旧版、候補、診断という名前やGitの未追跡・除外だけを理由に不要と判断しません。実施の順序は [制作手順の保存と整理](PRODUCTION.md#作業を区切るときの保存と整理)、画像の並行担当と来歴は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md) に従います。

| データの役割 | 保存・整理の扱い |
|---|---|
| 採用原本・再現用入力 | 原画、登録・校正、フォント・利用条件、台本、採用WAV・ゲート、実測timeline、master、動作情報、完成MP4・納品資料と依存先を保持する。旧版の中にある現行依存先も含める |
| 過去の採用媒体・仕様・制作記録 | 当時の採用・不備・検査範囲を示す履歴として保持する。現行はカタログと `CURRENT.txt` から案内し、旧記録を現在の合格内容へ書き換えない |
| 生成候補・不採用take・失敗試作 | 採用原本と区別し、入力・出力・採否理由と対応を保つ。画像の元生成物と候補は画像管理仕様に従う。採否・来歴・負の対照の根拠や制作記録から参照されるものを、候補という理由で削除しない |
| QA報告・比較資料・確認用画像／音声 | 対象SHA、方法、範囲、判断と結び付いた証拠を保全する。新しい検査は別の保存先へ置き、過去の結果や不合格の根拠を上書きしない |
| 再取得・再生成できる作業データ | `node_modules/`、仮想環境、モデル・Pythonキャッシュ、途中ダウンロード、描画中間画像、診断用生PCM等。作業中でなく、採用入力・来歴・QA証拠に使われず、再取得条件や再生成手順が残るものを整理候補にできる。完成検査後のraw frame stagingも個別に確認する |
| 未登録の持込資料 | `materials/` の原本と名前を保つ。現行作品とは独立し、新作へ採用する際に権利・出典と登録内容を確認する。未登録を不要と読み替えない |

raw frame stagingを削除する前に、必須入力・QA証拠からの参照がなく、稼働中でないことを確認します。残した `ffconcat` は描画済みPNGへの索引であり、PNG削除後の `encode-only` には再stageが必要です。削除範囲・SHA・再生成手順と確認結果を記録し、原画候補や過去の採用媒体を「古い」だけで削除しません。

元ゲームの `four-operations` 系リポジトリは別プロジェクトです。動画用に登録済みの素材・出典を使い、clone先から元ゲームへ暗黙に依存しません。既存の保存先を整理の都合で一斉に移動せず、内容が同じ二重保管を整理する場合も、残す正本・SHA・参照の対応を先に確認します。

パス表記だけが異なるものも、実体・正規化表記・OIDを照合してから整理し、表記差だけで別原本と判断したり画像を再保存したりしません。

Git共有対象は、対象checkoutのprofile・`.gitignore`・追跡状態を確認し、LFS属性は `.gitattributes` と照合してください。制作原本と公開用worktreeの同期・公開判定は [GitHub公開仕様](GITHUB-PUBLICATION.md) に従います。ローカルの保存対象とGit共有対象は別です。制作に必要な原本を消して容量を減らす方法は使いません。

## ローカル保存と他PCへの共有

ファイルがこのPCにあること、台帳へ登録したこと、Gitの保存対象であること、コミットしたこと、共有先へ反映したこと、別PCで取得・検証したことを別々に記録します。未追跡やGit除外の原本は、このPCに残っていても通常のcloneでは届きません。LFSポインタだけでは媒体の保存・取得確認になりません。

制作の再開には、上表の保存対象と、[作品別brief](../templates/production-brief.md) 等に残した担当・採用版・入力・出力先・検査結果・未完了の作業を使います。他PCへ渡す範囲は [再現用入力の更新手順](PRODUCTION.md#再現用入力をgitへ追加更新する) と [セットアップ](SETUP.md) に従い、Git/LFSの実体取得と必要なローカル動画の復元後に、参照とSHAを検証します。共有範囲外の候補や未登録資料も、唯一の原本を消さず、保管先と未共有であることを記録します。
