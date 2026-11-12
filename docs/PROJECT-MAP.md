# ファイル構成と正本

## 入口

| ファイル | 役割 |
|---|---|
| [`README.md`](../README.md) | 現行作品と別PC向けの入口 |
| [`SETUP.md`](SETUP.md) | ランタイム、入力、モデル、環境確認 |
| [`PRODUCTION.md`](PRODUCTION.md) | 出力標準、設計・再出力・音声採用・完成検査の実施工程 |
| [`IMAGE-ASSET-MANAGEMENT.md`](IMAGE-ASSET-MANAGEMENT.md) | 画像の担当・来歴・採用管理と、画風・精細さ・素材登録の受入条件 |
| [`LAYOUT-ALIGNMENT.md`](LAYOUT-ALIGNMENT.md) | 枠内の配置意図、実描画の測定、軸別許容差、配置QAの記録条件 |
| [`templates/production-brief.md`](../templates/production-brief.md) | 作品別の設計・担当・進捗・QA根拠・再開点を記入するひな形。共通条件は各正本を参照 |
| [`catalogs/character-asset-management-v1.json`](../catalogs/character-asset-management-v1.json)、[`character-asset-registry-v1.json`](../catalogs/character-asset-registry-v1.json) | 全キャラクター生成バッチの分類・担当・確定在庫と生成中の保留 |
| [`catalogs/library-v1.json`](../catalogs/library-v1.json) | 現行制作セットと採用素材の登録 |
| `reproducibility/production-inputs.json` | Gitへ収納する再現用入力とSHA-256 |
| `reproducibility/archive-policy.json` | 現行作品と依存先を保存する方針 |
| [`materials/README.md`](../materials/README.md)、[`materials/manifest-v1.json`](../materials/manifest-v1.json) | 未登録の持込資料と原本の目録 |
| [`reproducibility/organization-20261112-v001/manifest.json`](../reproducibility/organization-20261112-v001/manifest.json) | 整理対象・判断・実施結果・保存点と確認範囲の記録 |
| [`README.txt`](../README.txt)、[`PIPELINE.txt`](../PIPELINE.txt) | 過去の参照パスを保つ短い互換案内。手順本文は本表のMarkdown仕様へ統合 |

現行制作セットは `active_production_set_ids`、現行参照画像は `active_reference_set_ids` から辿ります。名前の版数や更新日時だけで採用版を判断しません。

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

| 設計フォルダ | 現行の主な資料 |
|---|---|
| `design/counting-video-v1/` | `production-spec-v2.txt`、`cue-sheet-v2.json`、`sound-cue-script-v2.txt`、`blue-sky-production-run-v002.json` |
| `design/binary-counting-v1/` | `production-spec-v005.txt`、`production-review-v005.txt`、`production-run-v005.json` |
| `design/octal-counting-v1/` | 発音調査、台本、`production-run-v002.json` |
| `design/hexadecimal-counting-v1/` | 発音調査、台本、明瞭なAの根拠、`production-run-v002.json` |
| `design/four-base-counting-v1/` | `CURRENT.txt`、`count-to-200-v002/`、`production-run-v002.json`、`production-review-v002.txt` |
| `design/even-counting-v1/` | `CURRENT.txt`、企画・台本、`production-run-v002.json`、`production-review-v002.txt`、`production-qa/v002-recheck-20261111/` |
| `design/odd-counting-v1/` | `CURRENT.txt`、キャラ抽選、`concept-and-scenario-v002.txt`、`script-and-sound-cues-v002.txt`、`production-run-v002.json`、`production-review-v002.txt` |
| `design/prime-counting-v1/` | `CURRENT.txt`、抽選、シナリオ・全英語台本、`production-run-v003.json`、`production-review-v003.txt`、`production-qa/v003-comparison/`。v001・v002の制作・検査記録も履歴として保存 |
| `design/fibonacci-counting-v1/` | `CURRENT.txt`、前工程、全41項・104発話、`production-run-v004.json`、`production-review-v004.txt`、現行104cue台本・全受渡し/導入/フェード・動作・音声継承の検査。v001/v002/v003の制作・検査記録も保全 |
| `design/collatz-counting-v1/` | `CURRENT.txt`、企画・真値・143cue台本、`production-v001/`、`production-run-v001.json`、`production-review-v001.txt`、全frame/454,238桁/音声・字幕と演出の独立検査 |
| `design/lucas-counting-v1/` | `README-production.md`、`CURRENT.txt`、41項・39加算の真値と104cue台本、`production-run-v001.json`、`production-review-v001.txt`。先行設計・不採用候補・失敗QAは当時の履歴として保全 |

`production-run*.json` は、完成品と採用素材・道具・検査記録のSHA-256を束ねます。来歴や検査に絶対パスが残っていても、実行時はリポジトリ内の採用先とマニフェストを使います。古い記録のパス文字列を書き換えるとhashで結ばれた来歴が変わるため、移植だけを理由に書き換えません。

## 動画の再出力に必要な入力

完成MP4だけでは再編集できません。少なくとも採用原画、フォント、実測 `timeline.json`、採用音声WAV、対応する採用・測定記録が必要です。採用 `master.wav` を再利用すれば、音声の再生成・再ミックスを省いて映像を再描画できます。

八進数、十六進数、4基数、偶数、奇数、素数、フィボナッチ動画では、作品固有の新しい台詞が元の `output/<作品>/speech/` にあります。元の `output/` は生成物と原本が混在していたため、別PCへ移す際は再現用入力の収納・復元手順に従ってください。フォルダ名だけを見て `speech/` や `timeline.json` を不要なキャッシュとして削除しないでください。

このリポジトリにはカタログの現行作品とその制作記録の依存先を収録します。収納対象と現在のファイル数・容量は `reproducibility/production-inputs.json` の `files`・`totals` に記録し、`tools/update_production_archive.py --check` で確認します。MP4、WAV、PNG、フォント等のバイナリはGit LFSで取得します。Gitへ収納した採用 `output/` 入力と、後で作る任意の `output/<新しい作業>/` を区別してください。

現行作品が旧作品の台詞や比較基準を再利用する場合は、その旧フォルダ内の原本も残します。フォルダ名が旧版でも、依存元であれば保存対象です。不要な旧音声マスター、キャッシュ、診断用生PCMまで一括で収納する構成ではありません。

現行完成品の元の保存先は次のとおりです。

| 作品 | 元の出力フォルダ |
|---|---|
| 十進数 | `output/counting-garden-001-bright-v002/` |
| 二進数 | `output/binary-counting-001-v005-number-gap2s/` |
| 八進数 | `output/octal-counting-001-v002-aligned-reading/` |
| 十六進数 | `output/hexadecimal-counting-001-v002-clear-A/` |
| 4基数 | `output/four-base-counting-001-v002-to-200/` |
| 偶数 | `output/even-counting-001-v002/` |
| 奇数 | `output/odd-counting-001-v002/`（1〜299、150値、8分55.80秒・16074フレーム） |
| 素数 | `output/prime-counting-001-v003/`（2〜997、168素数、11分26.33秒・20590フレーム、案内・拍手・休憩・進捗モザイク追加） |
| フィボナッチ | `output/fibonacci-counting-001-v004/production-v002/`（F₀〜F₄₀の41項、8分56.80秒・16104フレーム）。`timeline.json` と `character-motion.json` はv004、実測base・PCMマスター・合格AACと原音はv002の `audio-build/`・`speech/` を明示参照 |
| コラッツ | `output/collatz-counting-001-v001/delivery-v001/`（8分05.40秒・14562フレーム）。採用timeline/masterは同作品の`audio-build/`、原音・採用ゲートは`speech/`。専用再現手順は`design/collatz-counting-v1/production-v001/reproduction.txt` |
| リュカ数 | `output/lucas-counting-001-v001/render/full-v002/`（制作セットの初採用v001、8分59.53秒・16186フレーム）。字幕・章・公開用文面を同梱。実測timeline/masterは`audio-build/`、採用原音とゲートは`speech/` |

各出力には完成MP4、字幕、チャプター、アップロード文、最終QA等があります。4基数動画は `bird-motions.json` も描画に必要です。素数v003は `kangaroo-motion.json` と `assets/library/characters/kangaroo/animations/prime-v002/registration.json` を使います。新規12原画・既存15原画の計27原画を、2つの再利用名を含む29状態として登録し、470px高・足支点 `(1625, 1014)` で描画します。通常の完成品検査は `output/prime-counting-001-v003/qa/v001/verification.json`、教材・演技・進捗の独立検査は `design/prime-counting-v1/production-qa/v003-comparison/final-003/verification.json` に保存しています。AACはv002からコピーし、v001とも内容・時刻が完全一致するため、v001・v002フォルダ内のMP4・PCM・音声原本・タイムラインも再現依存先として保全します。

## ツールの対応

| 工程 | 主なツール |
|---|---|
| 別PCの環境確認・再出力 | `tools/portable_production.py` |
| 素材・台帳・ID・QA参照・LFS実体の全体検査 | `tools/verify_workspace.py` |
| 再現用入力の管理 | `tools/update_production_archive.py` |
| 固定モデルの取得・検証 | `tools/portable_models.py` |
| 設計準備 | `video_pipeline.py`、`prepare_*_episode.py`、`build_*_episode.py` |
| 背景・キャラ・数値のモック | `render_*_mockups.py` / `.mjs` |
| 動画描画 | `render_counting_video.py`、`render_binary_video_v003.py`、`render_octal_video.py`、`render_hexadecimal_video.py`、`render_four_base_video_v002.py`、`render_even_video_v002.py`、`render_odd_video_v002.py`、`render_prime_video_v003.py`（素数v001・v002の描画コードも維持）、`render_fibonacci_video_v004.py`（v001/v002/v003コードも保全） |
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
| 再取得・再生成できる作業データ | `node_modules/`、仮想環境、モデル・Pythonキャッシュ、途中ダウンロード、描画中間画像、診断用生PCM等。作業中でなく、採用入力・来歴・QA証拠に使われず、再取得条件や再生成手順が残るものを整理候補にできる |
| 未登録の持込資料 | `materials/` の原本と名前を保つ。現行作品とは独立し、新作へ採用する際に権利・出典と登録内容を確認する。未登録を不要と読み替えない |

元ゲームの `four-operations` 系リポジトリは別プロジェクトです。動画用に登録済みの素材・出典を使い、clone先から元ゲームへ暗黙に依存しません。既存の保存先を整理の都合で一斉に移動せず、内容が同じ二重保管を整理する場合も、残す正本・SHA・参照の対応を先に確認します。

パス表記だけが異なるものも、実体・正規化表記・OIDを照合してから整理し、表記差だけで別原本と判断したり画像を再保存したりしません。

Git LFSの対象はルートの `.gitattributes`、追加する原本と除外する作業データの設定は `.gitignore` を確認してください。制作に必要な原本を消して容量を減らす方法は使いません。

## ローカル保存と他PCへの共有

ファイルがこのPCにあること、台帳へ登録したこと、Gitの保存対象であること、コミットしたこと、共有先へ反映したこと、別PCで取得・検証したことを別々に記録します。未追跡やGit除外の原本は、このPCに残っていても通常のcloneでは届きません。LFSポインタだけでは媒体の保存・取得確認になりません。

制作の再開には、上表の保存対象と、[作品別brief](../templates/production-brief.md) 等に残した担当・採用版・入力・出力先・検査結果・未完了の作業を使います。他PCへ渡す範囲は [再現用入力の更新手順](PRODUCTION.md#再現用入力をgitへ追加更新する) と [セットアップ](SETUP.md) に従い、Git/LFSの実体取得後に参照とSHAを検証します。共有範囲外の候補や未登録資料も、唯一の原本を消さず、保管先と未共有であることを記録します。
