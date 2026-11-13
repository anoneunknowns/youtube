# GitHub公開仕様

制作原本を保全しながら、採用済みの非動画と必要な依存だけをGitHubへ反映する手順です。素材の採用・品質は [画像管理仕様](IMAGE-ASSET-MANAGEMENT.md)、作品の採用入力・再現は [制作仕様](PRODUCTION.md)、別PCでの取得は [セットアップ](SETUP.md) に従います。

## 制作原本と公開版を分ける

| 対象 | 保管・選択の扱い |
|---|---|
| 制作原本 | 採用・再制作・現在の検査に必要な原画、媒体と記録を保全する。不要旧版の明示削除は画像管理仕様に従う |
| 公開用worktree | 明示した採用素材と現行作品の必要な依存から、非動画の公開集合を作る |
| 別PCのclone | 公開集合とLFS本体を取得する。公開対象外の動画・候補・履歴まで取得できるとは扱わない |

制作原本の `main` と公開用ブランチは収録範囲や履歴が異なります。制作原本をそのままpushしたり、merge・reset・force pushで公開版へ合わせたりしません。公開profileを制作原本へコピーすると原本の検査範囲まで変わるため、各checkoutで独立して管理します。現在のローカル配置は [セットアップ](SETUP.md#制作原本とgithub公開用checkout) を参照してください。

共通素材の現行選択は `catalogs/character-adoptions-v1.json`、`catalogs/character-library-v1.json`、`catalogs/asset-library-current-v1.json` と各 `current/asset.json` で辿ります。作品の現行採用は `catalogs/library-v1.json` の `active_production_set_ids` と制作記録で辿ります。共通素材を更新しても、公開中の作品の採用入力を自動で置き換えません。素材だけを同期するときは、制作原本で並行更新された作品カタログ・作品表・制作記録を丸ごとコピーしません。

## 公開集合と内容の正本

公開用checkoutには次の記録を置きます。制作原本には存在しない場合があります。

| 記録 | 役割 |
|---|---|
| `catalogs/github-publication-v1.json` の `files` | 公開するファイルの正確な集合 |
| 同じprofileの `character_library_files` | 素材専用bundleにも必要な集合。runtime・再構築・exportの依存を満たす |
| `catalogs/character-library-files-v1.json` | 選択された素材ファイルの実体SHA-256・byte数 |
| `reproducibility/github-publication-files-v1.json` | 公開集合全体の実体SHA-256・byte数。自身のhashは含めない |
| `.gitignore` / `.gitattributes` / Git index | 公開集合の追跡・除外とLFS属性。属性だけでは本体の保存を証明しない |

更新時は既存 `character_library_files` の収録範囲を明示prune以外すべて保ち、追加分を用途で選びます。profile等を「制御用だから不要」と一律に除去せず、素材readerとZIP書出しの必須依存で確認します。profile自身が素材bundleの必須入力になる場合があります。`character-library-files-v1.json` の `files` ハッシュ行には自身を入れませんが、profileへそのpathを載せることや、ZIPへ当該JSONを同梱することとは別です。制御ファイルを一律追加・除去せず、現在の仕様と依存を照合します。

`reproducibility/production-inputs.json` と `archive-policy.json` はローカル動画を含む制作原本の保存・再現用です。GitHubの公開集合と同一視せず、公開漏れを理由に原本を削除したり期待SHAを書き換えたりしません。

配布用の素材ZIPは公開用checkoutから作ります。profileのない制作原本でのexportは、そのcheckoutのローカル在庫を収録する別の保存範囲です。候補・履歴を含む原本用exportを、公開用ZIPとして配布しません。

## ファイルを選ぶ

動画コンテナのMP4・MOV・MKV・WebM等は公開しません。MP3/WAV音声、PNG等の画像、GIFはこの動画除外には含めません。候補batch一式、不採用画像、現行で未使用の旧revisionも新たに収録しません。公開から外すことと、制作原本から削除することは別です。不要旧版を両方から削除する指示がある場合は、[画像管理仕様の削除手順](IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合)に従い、各checkoutの依存を独立に保護して対象パスと旧SHAを記録します。通常の削除commitは過去のGit履歴やLFS保存容量の回収を保証しません。

版番号が古くても、現行作品の音声・タイムライン・原画・登録・フォント・利用条件・QA根拠などから必要なら保ちます。削除前に、共通素材と公開中の作品の両方について、選択された入力・登録・実際のrenderer/importを確認します。古いcollectionの一覧だけに現れるパスは、それだけで現在の採用にはなりません。

依存は登録のframe/source sheet、通常姿、明示された生成入力・プロンプト、source manifestの採用file一覧、採用根拠などの契約から辿ります。JSON内の全文字列を再帰的に探し、歴史的な入力パス・絶対パス・候補のSHAを現在のruntime依存と読み替えません。生成時の旧画像参照は役割・path・SHAのmetadataとして保全でき、その記載だけで旧PNGを公開へ追加しません。登録横の補助ファイル名は登録ファイルからの相対位置で解決し、履歴上の絶対パスを実行先として試しません。

部分的な採用変更では、残る素材を支える過去の `selection_evidence` を新しい採用記録から消しません。旧根拠は公開baselineのentry全体とSHA・byte数が一致する実体を保持し、新しい根拠だけを正式パッケージ内へ追加します。来歴JSONの保全と、そこに記された旧画像の配布を分けます。

パスは正規のroot相対パスにし、symlinkを辿る公開先・親ディレクトリを使いません。Unicode正規化や大文字小文字の扱いで複数のGit pathが同じ実体を指す場合は、path表記・OID・byte内容を照合します。既存aliasが同じbyteであることを保ち、表記差だけで別素材として再保存・上書き・削除しません。

## 同期計画を固定する

1. 原本の採用・QAと登録を確定し、対象ID、原画・登録・INDEX/master・採用根拠のSHAを記録する。生成中や他担当の更新を混ぜない。
2. 公開先のrepository、HEAD、branch、clean状態、profile、receiptを確認し、今回のbaselineとして固定する。原本・公開の同名カタログが同じ作品選択だとは仮定しない。
3. `copy`、`prune`、文書の `patch`、再生成metadataをpath単位で列挙し、用途と変更前後SHAを束縛したplanを作る。未知の入力や未分類のファイルは都合よく除外・追加せず停止する。
4. 他素材のPNG、通常姿、継続利用するポーズ・登録尺度・支点、作品カタログと作品入力を保全対象にする。文書の一部だけが対象なら、公開版へその差分だけを当てる。

文書も公開checkoutのカタログと収録集合に照合します。「現行作品」の表、再出力例、採用版の説明は公開版の実体を保持し、制作原本の表や参考リンクを無条件にコピーしません。原本専用の資料を参考として挙げる場合は「公開版には未同梱」と明記したcode表記のパスにし、存在しない相対リンクを公開物の入口として案内しません。

profile全体の差分からinstall対象を自動拡大しません。書込対象は承認したcopy・patch・生成metadataの集合だけ、削除は明示pruneだけに限定します。新規pathに不明な既存ファイルがあれば上書きしません。

公開操作は1担当が直列で行います。原本と公開先のSHA・HEAD・branch・cleanを検証後とinstall前に再照合し、各replace/unlinkの直前にも対象のSHAを比較するCASを行います。新規ファイルはcreate-onlyにし、途中で別ファイルが現れたら停止します。許可集合外の公開worktree変更も検出し、既存の他作業を古いsnapshotへ巻き戻しません。

## 独立したtreeで検証する

計画の実行検証は公開worktreeとは別の保存先で行います。APFS等のCOW clone、または独立したコピーを使い、書込可能なhardlinkを共有しません。検証処理がin-place更新へ変わっても、原本や公開worktreeへ漏れない構造にします。

隔離treeにplanを適用し、profileとexact allowlistの `.gitignore` を作り、currentビュー・INDEX/master・file inventoryを整合させます。画像は再エンコードせず、採用PNGのbyte-copyまたは登録に従う無損失切り出しを保ちます。承認INDEX/masterのSHA、未変更PNG、作品カタログ・入力、許可集合外の全公開ファイルをbaselineと比較します。

次は**隔離treeを作り終えた後、そのtreeのルートで**行う既存ツールの例です。`python` はPillowを導入済みのインタープリターを使います。build/refreshは隔離tree内の派生ファイルを書き換えます。

```sh
python tools/unified_asset_library.py build
python tools/character_library.py refresh
python tools/unified_asset_library.py verify
python tools/character_library.py verify
```

ここまでの派生ファイルを確定してから、確認済みの同期実装で全体receiptを実体から再生成し、その後に次を実行します。build/refresh後の古いreceiptのまま公開検査へ進みません。公開検査ツールは読取検査用であり、receiptを書き出すオプションはありません。

```sh
python tools/verify_github_publication.py
```

`verify_github_publication.py` は公開用checkoutにある検査ツールです。制作原本にない場合も、別の全履歴検査で代用したりprofileを原本へ置いたりしません。素材専用exportが必要な場合も同じprofileのclosureで検証し、既存の必須membershipを削って通しません。

隔離検証が通った後に同じplan/SHAで限定installします。複数ファイルの更新は一括transactionではありません。途中失敗や競合時は、plan・失敗tree・receipt・実際のdiffを残し、適用済みの範囲と原因を確認してから次の計画を作ります。部分適用へ同じ処理を無条件に再実行したり、失敗の証拠を成功記録で上書きしたりしません。

## LFS・Git index・公開先を確認する

Gitへ記録されたLFS pointerと、開ける本体は別です。別PCでは `git lfs pull` と `git lfs fsck` を使い、画像のsignature・寸法・SHAを採用記録と照合します。PNGをブラウザで表示できたことだけで、LFS取得やnative pixelの一致を証明しません。全動画の復元が必要な制作検査は [セットアップ](SETUP.md) に従って別途行います。

以下は制作原本のルートから、現在のローカル公開用配置を検査する例です。別の配置では変数を実際の公開先へ変更します。

```sh
publication_root=.work/github-current-publication
git -C "$publication_root" status --short --branch
git -C "$publication_root" rev-parse HEAD
git -C "$publication_root" branch --show-current
git -C "$publication_root" lfs fsck
python "$publication_root/tools/verify_github_publication.py" --check-git
```

stageはplanの明示pathと削除だけを対象にし、無関係なuntrackedファイルを一括追加しません。`--check-git` が照合するのはGit indexのpath集合です。index内の内容の一致は別に確認し、LFS対象では `git show :<path>` 等で得たpointerの `oid sha256`・sizeを、確認済み本体のSHA・byte数へ照合します。通常の文書やJSONもstage済みblobと確認済み内容を比べ、working treeだけの成功をcommit内容の保証にしません。動画・新規候補batch・不要旧版の混入がなく、保全対象のSHAが一致したことを記録して公開用ブランチでcommitします。

公開は確認済みの公開worktreeから、送り先を明示した通常pushで行います。

```sh
git -C "$publication_root" push origin HEAD:main
```

pushが拒否されたらforceで回避せず、remote更新と手元のplanとの差を確認します。完了後は接続済みGitHubツール等でremote `main` のcommitを確認し、今回の公開commitと一致するか照合します。さらに変更したPNGと必要な代表PNGを `https://media.githubusercontent.com/media/<owner>/<repository>/<commit>/<path>` のcommit固定URLから取得し、HTTP status・PNG signature・寸法・SHAをlocal currentおよび採用原画と比較します。対応する `asset.json`・INDEX・共通台帳も同じcommitのJSONを取得し、ファイルのSHAと画像・登録への参照を照合します。branch URLだけの確認や、LFS大容量全体の再ダウンロードで代用しません。

## 認証と記録の扱い

既存の `gh` 認証またはGit credential helperを使います。診断やログへtoken・password・Authorization header・認証を含むURLを表示せず、credentialの一覧や秘密値をダンプしません。公開作業のために永続的なGit認証設定・remote URL・OS設定を変更せず、必要な実行環境は作業プロセスに限定します。

実施記録はsource/PUBのbaseline、planと実装のSHA、copy/prune/patch集合、隔離検証、保全対象、LFS/Git index照合、公開commitと取得結果を束ねます。個別作業のID・commit・hash・件数はその記録に置き、今後の採用条件や公開件数の固定値にしません。
