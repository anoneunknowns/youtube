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
| クマ以外10種類・新規270姿勢と動作プレビュー | [`assets/library/collections/character-expansion/v001/`](assets/library/collections/character-expansion/v001/) |
| 大きい表示枠の8種・紅茶／ジャンプ等のアイキャッチ144姿勢 | [`assets/library/collections/character-eyecatches/v001/`](assets/library/collections/character-eyecatches/v001/) |
| 全キャラクター生成バッチの担当・用途・候補・品質指摘 | [`画像管理一覧`](assets/library/character-assets.html)、[`管理仕様`](docs/IMAGE-ASSET-MANAGEMENT.md) |
| 素数v003用カンガルー・新規12原画、27原画・29状態の登録 | [`assets/library/characters/kangaroo/animations/prime-v002/registration.json`](assets/library/characters/kangaroo/animations/prime-v002/registration.json) |
| 全保管ファイルのサイズ・ハッシュ | [`catalogs/character-library-files-v1.json`](catalogs/character-library-files-v1.json) |
| 一覧・検証・プレビュー・素材専用ZIPの作成 | [`tools/character_library.py`](tools/character_library.py) |

11種類の通常姿、従来42姿勢、拡充270姿勢、アイキャッチ144姿勢を利用できます。各キャラクターの採用パスと登録座標は台帳、一覧と使い分けは[素材の利用案内](assets/library/README.md)を参照してください。

画像・GIFはGit LFSで管理しています。素材だけを取得する場合は、初回clone時のLFS自動取得を止めたうえで、`assets/library/characters/**` と素材collection・管理監査資料を対象に `git lfs pull` を実行します。画像本体を取得後、リポジトリのルートから次を実行してください。

```powershell
git lfs pull --include="assets/library/characters/**,assets/library/collections/**" --exclude=""
python -m pip install -r requirements.txt
python tools/character_library.py list --json
python tools/character_library.py verify
python tools/character_library.py preview --character red-panda --pose cheer --height 430 --output D:/temp/red-panda-cheer.png
python tools/character_library.py export --output D:/temp/num-num-character-library.zip
```

出力先は取り込み先の環境に合わせて変更してください。`export` のZIPは、11種類の通常姿、従来・拡充動作、アイキャッチ、台帳、生成条件、検証記録、ツール、依存指定をまとめた素材専用パッケージです。取り込み時は画像だけを抜き出さず、台帳・登録情報と相対配置を一緒に維持してください。動画本体や音声モデルのキャッシュは不要です。

台帳の `path_base` は `library-root` です。通常姿の `image_region_px`・`anchor_px`・`reference_height_px`、動作の `key_poses.poses`・`common_reference_height_px` を使って描画します。ウサギの通常姿はシート内の指定領域であり、単独PNGとしてシート全体を使わないでください。同じ動物の動作には共通の縮尺と足支点を使い、屈伸やついばみ姿勢を個別の画像高さで拡大しません。オナガドリは身体で縮尺を決め、長い尾の領域を別に確保します。

`generation-prompt.txt`・`generation-input.json`・`source-manifest.json`・`registration.json` と各collectionの `qa-evidence/` は、派生素材を作る際の根拠です。過去の生成先 `C:/...` や `D:/temp/...` は履歴であり、現在のPCに存在する前提にしません。採用原画を上書きせず、修正版は新しい版として保存します。キーポーズの補間・音声同期・余白は実際の取り込み先の画面で確認してください。利用条件は各素材・依存物の既存記録を確認し、この説明から新たな利用許諾を推定しないでください。

## 現行の9作品

現行版の判定は [`catalogs/library-v1.json`](catalogs/library-v1.json) の `active_production_set_ids` を使います。素材の `v001` が旧素材を意味するとは限りません。

| 作品 | 範囲・音声 | キャラクターと背景 | 完成尺 | 制作記録 |
|---|---|---|---|---|
| 十進数カウント | 1〜300、十進数の自然な英語読み | 赤い帽子のクマ・青空の庭 | 8分16.97秒 | [青空版v002](design/counting-video-v1/blue-sky-production-run-v002.json) |
| 二進数カウント | 0〜1111111₂、各桁を英語で読む | 同じクマ・夕暮れの庭・十進数看板 | 21分31.10秒 | [v005](design/binary-counting-v1/production-run-v005.json) |
| 八進数カウント | 0〜177₈、各桁を英語で読む | ピンクのウサギ・オーロラの庭 | 10分42.97秒 | [配置修正版v002](design/octal-counting-v1/production-run-v002.json) |
| 十六進数カウント | 0〜7F₁₆、数字とA〜Fを読む | とら・星空の天文台 | 9分22.73秒 | [明瞭なAへ改訂したv002](design/hexadecimal-counting-v1/production-run-v002.json) |
| 4基数同時カウント | 十進0〜200を2・10・8・16進数で表示、音声は十進数 | 小鳥・海辺の灯台 | 11分02.37秒 | [200までのv002](design/four-base-counting-v1/production-run-v002.json) |
| 偶数カウント | 0〜200を2ずつ、全101値、自然な英語読み | 小鳥・木のおもちゃ工房 | 6分09.00秒 | [語頭・図切替修正版v002](design/even-counting-v1/production-run-v002.json) |
| 奇数カウント | 1〜299を2ずつ、全150値、自然な英語読み | レッサーパンダ・山のケーブルカー駅 | 8分55.80秒 | [299までのv002](design/odd-counting-v1/production-run-v002.json) |
| 素数カウント | 1000未満の全168素数、2〜997、自然な英語読み | カンガルー・日差しの入るモザイク博物館 | 11分26.33秒 | [案内動作・進捗追加v003](design/prime-counting-v1/production-run-v003.json) |
| フィボナッチ数列 | F₀=0〜F₄₀=102,334,155の41項、式の前半と結果を自然な英語で読む | シャム猫・雲の上の風の郵便局 | 8分56.80秒 | [完成v003](design/fibonacci-counting-v1/production-run-v003.json) |

4基数の小鳥動画は全201値・804表記、通常の数の読み終わりから次の読み始めまで197か所を2秒、説明を挟む3か所を5秒にしています。偶数動画は全101値、通常98境界を2秒、20と100の後の確認2境界を10秒にしています。桁読み動画の「桁間0.9秒」を、自然な十進数の語の間へ挿入しないでください。

新作はショート動画以外は原則1本8分以上とします。数の間隔や読み速度を変えて尺を延ばさず、通常2秒の間隔を保ち、区切りのよい終点まで範囲を広げます。Shortsまたはユーザーの明示した例外だけを別扱いにし、過去の完成品は当時の尺を維持します。詳しくは [制作手順](docs/PRODUCTION.md) を参照してください。

奇数v002は範囲を299まで広げ、通常147境界を2秒、9と101の後の確認2境界を10秒にします。切符を組にして一つ余ることと、99に2を足すと101になることを示します。レッサーパンダは尾を含む通常姿を使い、BGMと効果音は入れません。

素数動画は陶片の行・列で5と6を比較し、1の除外・2だけが偶数の素数・9と97→101を説明します。通常164境界は2秒、説明3境界は18秒で、BGM・効果音はありません。v003では新規12原画と既存15原画の計27原画を使い、2つの再利用名を含む29状態を登録しました。頭・下半身・尾を保つ腕の部分合成で手振りを修正し、教材を示す3姿・拍手3姿と、約12秒の座る→伸びる→休む→立つ流れを追加しています。キャラクターは470px高・足支点 `(1625, 1014)`。各素数の読み終わりに1枚ずつ増える168枚の進捗モザイクで、通算順位と終幕をつなぎます。シート共通の身体基準と足支点を使い、姿勢ごとの高さに合わせて拡大しません。

現行MP4は [`output/prime-counting-001-v003/paspla-studio-prime-numbers-2-to-997-1080p.mp4`](output/prime-counting-001-v003/paspla-studio-prime-numbers-2-to-997-1080p.mp4) です。168素数・188発話・全20,590フレームを維持し、教材・演技・進捗を独立に再検査しました。v002の最終AAC（v001と同一）を再エンコードせずコピーし、全32,173パケットのビット列・時刻の一致を確認しています。検査範囲と結果は [制作レビュー](design/prime-counting-v1/production-review-v003.txt) に保存しています。自動解析と抽出画像の確認による結果であり、全編を人が連続視聴・試聴したという記録ではありません。`python tools/portable_production.py preview --production prime --out-dir output/new-prime-preview` でプレビューできます。静止版[v001の制作記録](design/prime-counting-v1/production-run-v001.json)と、動作追加版[v002の制作記録](design/prime-counting-v1/production-run-v002.json)、それぞれのMP4・採用音源・検査記録は履歴と再現依存先として保全しています。

フィボナッチ動画は、二つの入力から足し算で次の値を生成し、新しい二項を次の計算へ渡します。0と二つの1を保持し、39回の加算で全41項を数えます。v002で追加した手振り・気づきの5姿勢と明瞭な46,368の全文音声を維持し、v003ではF20の受渡し中に二数値を88→47pxへ縮めて次式へつなぐ瞬間縮小を解消しました。[現行台本](design/fibonacci-counting-v1/scenario-v003.txt)・[制作レビュー](design/fibonacci-counting-v1/production-review-v003.txt)・[音声継承検査](output/fibonacci-counting-001-v003/audio-inheritance-qa/v001/final-audio-review.json)に実際の画面と検査範囲を保存しています。`python tools/portable_production.py render --production fibonacci --out-dir output/new-fibonacci-render` で全編を再出力できます。合格AACは測定済みマスター・実測タイムラインへSHAで束縛してコピーします。v001/v002の完成品と当時の検査記録も保全しています。

## 最初に行うこと

1. [セットアップ](docs/SETUP.md) に従い、素材・再現用入力と必要なランタイムを取得する。
2. `python tools/verify_workspace.py` で素材・台帳・参照・LFS実体を点検し、`python tools/update_production_archive.py --check` と `python tools/portable_production.py doctor` で再現用入力と環境を確認する。
3. `python tools/portable_production.py list` で現行の制作セットを確認する。
4. 静止画プレビューを確認し、新しい出力先へ動画を書き出す。
5. 完成MP4の数値・同期・音声・レイアウトを検査する。

新作を始めるときは [制作手順](docs/PRODUCTION.md#新作の設計) に従い、[制作ブリーフのひな形](templates/production-brief.md) へ作品ごとの設計・担当・検査記録をまとめます。

既存の完成品や採用音声へ上書きせず、新しい出力先を使います。旧 `README.txt` と `PIPELINE.txt` は過去の参照パスを保つ互換案内へ整理しました。手順は本READMEと `docs/`、各版の根拠は作品別の制作記録を参照してください。

## 正本と検査記録

- [`catalogs/library-v1.json`](catalogs/library-v1.json)：現行作品と採用素材の登録。
- [`design/`](design/)：脚本、発音調査、制作仕様、絵コンテ、制作記録。
- [`assets/library/`](assets/library/)：再利用する原画、背景、動作、フォント、効果音、検査済み音声と利用条件。
- [`tools/`](tools/)：設計準備、音声合成・検査、動画描画、字幕出力、最終検査。
- [`tests/`](tests/)：時刻計算、音声採用ゲート、配置等の回帰検査。

偶数動画は [制作記録](design/even-counting-v1/production-run-v002.json) と [再検査・修正結果](design/even-counting-v1/production-qa/v002-recheck-20261111/verification.txt) を参照してください。再検査で見つけた6語の語頭と説明図の文字重なりをv002で修正しました。全11070フレームの追跡、独立した全101値・505欄、最終AAC全115発話の新規ASR・CTC、原音との左右波形照合、字幕を確認しています。回帰テスト163件も通過しています。検査は自動解析と抽出画像の確認を含み、全編の人による試聴・視聴を行ったという記録ではありません。

4基数動画の [制作記録](design/four-base-counting-v1/production-run-v002.json) と [独立再検査](design/four-base-counting-v1/production-qa/v002-recheck-20261111/verification.json) も保存しています。

奇数動画は全16074フレームの主数値・英語読み・7整数の数直線、原寸の切符の組・99から101への説明・中間フェード、全163発話の原音との左右照合と字幕を検査しました。最終AACの新規ASR・CTCと音響情報、独立した再デコード・発音差分確認も合格し、回帰テスト204件が通過しています。[制作記録](design/odd-counting-v1/production-run-v002.json) と [最終検査](design/odd-counting-v1/production-qa/v002/verification.txt) に根拠と実施範囲を保存しています。検査は自動解析と抽出画像の確認を含み、全編を人が連続試聴・視聴したという記録ではありません。

移植手順は同じWindows上の別のGit/LFSチェックアウトで検証しました。137件のテスト、全5作品のプレビュー、新しい音声の生成・ASR・CTC、旧パスを持つ採用音声の参照解決を確認しています。[検証記録](reproducibility/validation-20261111/verification.json) に実施範囲と根拠を保存しています。

## 利用条件

モデル、フォント、外部ライブラリ等の条件は、各素材の出典と個別の利用条件を確認してください。音声関連は [モデルカード](assets/library/audio/speech/kokoro-af-heart/v002/model-card.md)、[v002のライセンス](assets/library/audio/speech/kokoro-af-heart/v002/licenses/)、[二進数用ライブラリのライセンス](assets/library/audio/speech/kokoro-af-heart/binary-v001/licenses/)、フォントは [M PLUS Rounded 1cのOFL](assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-OFL.txt) から辿れます。

このREADMEは画像・音声・キャラクターへ新しい再配布ライセンスを付与しません。
