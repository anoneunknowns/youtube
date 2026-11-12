# Num-Num Numbers — 画像素材ライブラリと動画制作

Paspla StudioのNum-Num Numbersで使う、透過画像・ポーズ・動作をまとめた素材ライブラリです。全19種類を同じ台帳とフォルダ構造で管理しています。他のプロジェクトでは、使いたいPNGを1枚選ぶところから利用できます。

画像の入口は[素材一覧・利用ガイド](assets/library/README.md)、AI向けの機械可読な入口は[共通素材台帳](catalogs/asset-library-current-v1.json)です。[素材を扱うAIへの指示](assets/library/AGENTS.md)には、画像の選び方・支点・共通縮尺・出典の扱いをまとめています。

このリポジトリでは数を学ぶYouTubeシリーズの企画、英語台本、背景、採用音声、描画・検査ツール、制作記録も管理します。制作する場合は[セットアップ](docs/SETUP.md)、[制作手順](docs/PRODUCTION.md)、[ファイル構成](docs/PROJECT-MAP.md)を参照してください。

## 他プロジェクトのAI向け：キャラクター素材の場所と利用方法

### 素材を選ぶ

19種類・通常姿19枚・ポーズ505枚、計524ファイルの透過PNGを、[一つの素材一覧](assets/library/README.md)から選べます。クマ、ウサギ、とら、小鳥、シャム猫、レッサーパンダ、ミーアキャット、カンガルー、ハリネズミ、ヤイロチョウ、オナガドリ、草、花壇、飛行機、ロケット、ヘリコプター、蝶、てんとう虫、虹を収録しています。

各IDは同じ構造です。通常姿はそのまま使えるPNGで、シートからの切り出し作業は済んでいます。

```text
catalogs/asset-library-current-v1.json
assets/library/characters/<id>/current/
  asset.json
  neutral.png
  poses/<namespace>/<pose>.png
  clips.json
```

| 使いたいもの | 読む場所 |
|---|---|
| 画像を1枚使う | 素材一覧のPNGリンク、または各IDの `current/neutral.png` |
| 表情・姿勢のPNGを選ぶ | `current/asset.json` の `poses` にある名前と画像パス |
| 動作を組む | `current/clips.json` のフレーム列・時間・効果と、各PNGの登録情報 |
| 全ID・manifestの場所・SHA-256 | `catalogs/asset-library-current-v1.json` の `assets` |
| 原画・生成条件・画風や品質の確認資料 | `asset.json` の元データ参照と[素材ガイド](assets/library/README.md) |

### PNGを1枚取得する

画像だけを使う場合はPythonや動画制作ツールの導入は不要です。[全19種類の素材一覧](assets/library/README.md)から使うPNGを開いて保存できます。Git LFS管理のPNGをURLから取得するときは、画像実体のURLを使ってください。

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

`basic/` は反応・基本動作、`expanded/` は仕草・姿勢、`eyecatch/` は紅茶・おじぎ等の演技、`gimmick/` は背景に配置する素材の動作を表す名前空間です。各素材で使える名前は `asset.json` の `poses` を読んでください。互換ローダー `character_library.py` では `basic/` の接頭辞を省き、他は名前空間を付けます。

同じ場面の動作群は `scale = 表示する基準高 / reference_height_px` と登録済み支点で配置します。姿勢ごとの外接高さへ合わせて拡大すると体格が跳ねます。翼・尾・炎・回転翼を含む可視範囲の余白を確保し、各素材の `anchor_kind` と表示上限は[素材ガイド](assets/library/README.md)で確認してください。動作の時間が指定されていないclipは、使う場面で設計・確認します。

### 公開範囲と記録

GitHubで取得できるファイルは[公開対象一覧](catalogs/github-publication-v1.json)の `files`、原画・登録・確認資料を含む素材パッケージの範囲は `character_library_files` が正本です。現行素材と、その採用・利用に必要な入力・資料を公開します。採用中のファイルはフォルダの版番号に関係なく対象です。未使用の旧版・不採用候補・過去の完成品・動画ファイルはローカル保管です。台帳の履歴パスは配布ファイルの存在を保証しません。

画像・GIF・音声（WAV・MP3等）・フォントはGit LFSで管理します。素材だけを使う際に動画本体・音声モデル・Node.jsは不要です。ファイル整合、過去の採用、現在の画風・動作品質は各確認記録で区別し、取得漏れを隠すためのハッシュ書換えは行いません。利用条件は[素材ガイド](assets/library/README.md)と各依存物の記録を参照してください。

## 現行作品

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
| 素数カウント | 1000未満の全168素数、2〜997、自然な英語読み | カンガルー・日差しの入るモザイク博物館 | 11分26.33秒 | [案内動作・進捗追加v003](design/prime-counting-v1/production-run-v003-publication-v002.json) |
| フィボナッチ数列 | F₀=0〜F₄₀=102,334,155の41項、式の前半と結果を自然な英語で読む | シャム猫・雲の上の風の郵便局 | 8分56.80秒 | [完成v004](design/fibonacci-counting-v1/production-run-v004.json) |
| コラッツ数列 | 7→1と27→1、全129項・127演算、自然な英語読み | ハリネズミ・しずくの計算水路 | 8分05.40秒 | [完成v001](design/collatz-counting-v1/production-run-v001.json) |
| 平方数の数列 | 0²〜100²=10,000の101項、乗算の前半と結果を英語で読む | レッサーパンダ・昼の凍った湖 | 10分46.83秒 | [完成v001](design/square-counting-v1/production-run-v001.json) |
| 2の累乗の数列 | 2⁰〜2⁶⁴の65項、64回の倍増と結果の自然な英語読み | ヤイロチョウ・紙と影の倍々劇場 | 9分25.13秒 | [完成v002](design/powers-of-two-counting-v1/production-run-v002.json) |
| 等比数列 | 初項2・公比3、全41項・40演算、比較例のSixを明瞭化 | ピンクのウサギ・色ガラスの倍率回廊 | 11分21.87秒 | [完成v002](design/geometric-sequence-counting-v1/production-run-v002.json)／[再出力案内](design/geometric-sequence-counting-v1/production-v002/reproduction.txt) |
| リュカ数 | L₀=2、L₁=1〜L₄₀=228,826,127、41項・39加算と結果の英語読み | ミーアキャット・昼のからくり時計塔 | 8分59.53秒 | [完成v001](design/lucas-counting-v1/production-run-v001.json)／[制作レビュー](design/lucas-counting-v1/production-review-v001.txt) |

4基数の小鳥動画は全201値・804表記、通常の数の読み終わりから次の読み始めまで197か所を2秒、説明を挟む3か所を5秒にしています。偶数動画は全101値、通常98境界を2秒、20と100の後の確認2境界を10秒にしています。桁読み動画の「桁間0.9秒」を、自然な十進数の語の間へ挿入しないでください。

新作はショート動画以外は原則1本8分以上とします。数の間隔や読み速度を変えて尺を延ばさず、通常2秒の間隔を保ち、区切りのよい終点まで範囲を広げます。Shortsまたはユーザーの明示した例外だけを別扱いにし、過去の完成品は当時の尺を維持します。詳しくは [制作手順](docs/PRODUCTION.md) を参照してください。

奇数v002は範囲を299まで広げ、通常147境界を2秒、9と101の後の確認2境界を10秒にします。切符を組にして一つ余ることと、99に2を足すと101になることを示します。レッサーパンダは尾を含む通常姿を使い、BGMと効果音は入れません。

素数動画は陶片の行・列で5と6を比較し、1の除外・2だけが偶数の素数・9と97→101を説明します。通常164境界は2秒、説明3境界は18秒で、BGM・効果音はありません。v003では新規12原画と既存15原画の計27原画を使い、2つの再利用名を含む29状態を登録しました。頭・下半身・尾を保つ腕の部分合成で手振りを修正し、教材を示す3姿・拍手3姿と、約12秒の座る→伸びる→休む→立つ流れを追加しています。キャラクターは470px高・足支点 `(1625, 1014)`。各素数の読み終わりに1枚ずつ増える168枚の進捗モザイクで、通算順位と終幕をつなぎます。シート共通の身体基準と足支点を使い、姿勢ごとの高さに合わせて拡大しません。

現行MP4のローカル保管先は `output/prime-counting-001-v003/paspla-studio-prime-numbers-2-to-997-1080p.mp4` です。168素数・188発話・全20,590フレームを維持し、教材・演技・進捗を独立に再検査しました。v002の最終AAC（v001と同一）を再エンコードせずコピーし、全32,173パケットのビット列・時刻の一致を確認しています。検査範囲と結果は [制作レビュー](design/prime-counting-v1/production-review-v003.txt) に保存しています。自動解析と抽出画像の確認による結果であり、全編を人が連続視聴・試聴したという記録ではありません。`python tools/portable_production.py preview --production prime --out-dir output/new-prime-preview` でプレビューできます。v001・v002の完成品と当時の検査記録はローカル履歴です。現行版が継承する音声等の入力は、公開対象一覧にあるファイルを取得してください。

フィボナッチ動画は、二つの入力から足し算で次の値を生成し、新しい二項を次の計算へ渡します。0と二つの1を保持し、39回の加算で全41項を数えます。v004では猫の上下の視線、頷き、瞬きの6原画を追加し、計算・受渡し・説明と結び付く118の動作窓を組みました。途中の腕戻り3か所には中間姿勢を挟んでいます。F20の受渡し中の88→47px縮小、明瞭な46,368を含む全104発話と字幕時刻は保持しています。[現行台本](design/fibonacci-counting-v1/scenario-v004.txt)・[制作レビュー](design/fibonacci-counting-v1/production-review-v004.txt)・[音声継承検査](output/fibonacci-counting-001-v004/production-v002/audio-inheritance-qa/v001/final-audio-review.json)に実際の画面と検査範囲を保存しています。`python tools/portable_production.py render --production fibonacci --out-dir output/new-fibonacci-render` で全編を再出力できます。合格AACは測定済みマスター・実測タイムラインへSHAで束縛してコピーします。v001/v002/v003の完成品と当時の検査はローカル保管です。現行版が使う以前の版の入力は公開対象一覧に含みます。

平方数は同じ入力を二辺へ運び、正方形が満たされると答えが確定します。単位格子、L字の増築、32²の面積分割、100ブロックと拡大凡例を使い分けます。通常96境界は結果の読み終わりから次の式まで2秒です。[本制作の記録](design/square-counting-v1/production-run-v001.json)・[制作レビュー](design/square-counting-v1/production-review-v001.txt)に、固定音声からの二段再出力と独立検査の範囲を保存しています。画像生成16原画と21登録状態、本編使用15状態は区別し、未使用の旧候補と旧QAはローカル保管します。

コラッツ動画は、偶数の二分と奇数の三倍＋1を実際に動かし、計算途中の値を数列の項と区別します。完成MP4のローカル保管先 `output/collatz-counting-001-v001/delivery-v001/paspla-studio-collatz-sequence-7-and-27-1080p.mp4`、[制作レビュー](design/collatz-counting-v1/production-review-v001.txt)、[独立最終検査](design/collatz-counting-v1/production-qa/v001/final-006/verification.json)を保存しています。全129項・127演算、143字幕・最終AAC、原寸の両軸配置に加え、45万桁以上を0〜9候補で照合しました。再出力は専用の[再現手順](design/collatz-counting-v1/production-v001/reproduction.txt)を使います。従来9作品の`portable_production.py`アダプターとは別の入口です。

## 最初に行うこと

1. [セットアップ](docs/SETUP.md) に従い、素材・再現用入力と必要なランタイムを取得する。
2. `python tools/verify_github_publication.py` で公開対象・LFS実体を点検し、`python tools/portable_production.py doctor` で現行作品の再現用入力と環境を確認する。ローカルの全保管資料を検査する場合は `verify_workspace.py` と `update_production_archive.py --check` を使う。
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

偶数動画は [制作記録](design/even-counting-v1/production-run-v002.json) と、ローカル履歴の再検査・修正結果 `design/even-counting-v1/production-qa/v002-recheck-20261111/verification.txt` を参照してください。再検査で見つけた6語の語頭と説明図の文字重なりをv002で修正しました。全11070フレームの追跡、独立した全101値・505欄、最終AAC全115発話の新規ASR・CTC、原音との左右波形照合、字幕を確認しています。回帰テスト163件も通過しています。検査は自動解析と抽出画像の確認を含み、全編の人による試聴・視聴を行ったという記録ではありません。

4基数動画の [制作記録](design/four-base-counting-v1/production-run-v002.json) と、ローカル履歴の独立再検査 `design/four-base-counting-v1/production-qa/v002-recheck-20261111/verification.json` も保管しています。

奇数動画は全16074フレームの主数値・英語読み・7整数の数直線、原寸の切符の組・99から101への説明・中間フェード、全163発話の原音との左右照合と字幕を検査しました。最終AACの新規ASR・CTCと音響情報、独立した再デコード・発音差分確認も合格し、回帰テスト204件が通過しています。[制作記録](design/odd-counting-v1/production-run-v002.json) と、ローカル履歴の最終検査 `design/odd-counting-v1/production-qa/v002/verification.txt` に根拠と実施範囲を保存しています。検査は自動解析と抽出画像の確認を含み、全編を人が連続試聴・視聴したという記録ではありません。

移植手順は同じWindows上の別のGit/LFSチェックアウトで検証しました。137件のテスト、全5作品のプレビュー、新しい音声の生成・ASR・CTC、旧パスを持つ採用音声の参照解決を確認しています。ローカル履歴の検証記録 `reproducibility/validation-20261111/verification.json` に実施範囲と根拠を保存しています。

## 利用条件

モデル、フォント、外部ライブラリ等の条件は、各素材の出典と個別の利用条件を確認してください。音声関連は [モデルカード](assets/library/audio/speech/kokoro-af-heart/v002/model-card.md)、[v002のライセンス](assets/library/audio/speech/kokoro-af-heart/v002/licenses/)、[二進数用ライブラリのライセンス](assets/library/audio/speech/kokoro-af-heart/binary-v001/licenses/)、フォントは [M PLUS Rounded 1cのOFL](assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-OFL.txt) から辿れます。

このREADMEは画像・音声・キャラクターへ新しい再配布ライセンスを付与しません。
