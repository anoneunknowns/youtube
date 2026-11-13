# 赤いベレー帽のクマの共有素材

通常姿と18状態を同じ絵柄・身体尺度で扱う共有ストックです。画像利用の入口は `assets/library/characters/bear-beret/current/asset.json`、通常PNGは同じ場所の `neutral.png` です。ポーズは `poses/eyecatch/` から選びます。

通常姿は [採用原画](../../references/canonical-neutral-v002.png)、姿勢の正本は [registration.json](registration.json) です。18状態は新たに生成した15ポーズと、通常姿原画を再利用した3状態からなり、独立原画は16枚です。全PNGは1254×1254の透過RGBAで、生成出力または通常姿のバイト一致コピーです。輪郭やalphaの清掃は加えていません。

表示は共通の `reference_height_px: 1107` と各姿勢の `anchor_px` を使います。しゃがみ・前傾・傾き・脚をたたんだ姿勢を、その都度の外接矩形へ合わせて拡大しません。`jump_takeoff` と `jump_air` は推定地面を支点とし、描かれた足の浮きを保持します。追加の跳躍移動を重ねないでください。

原寸16原画、顔・手足などの細部、明暗の正しいalpha合成を確認しています。[静止検査](qa/native-static-review.json)と[表示配置検査](qa/display-layout.json)に、確認範囲と軽微な差を記録しました。外周の補助測定は身体高430px換算で約4.71〜5.73pxです。軽いお辞儀・お茶を持つ姿は少し強め、深いお辞儀は頭の投影幅が少し小さく見える点を記録しています。形崩れや余分な部品の判定と、線の細かな強弱を区別しています。

[明背景の一覧](pose-review.png)・[暗背景の一覧](pose-review-dark.png)・[キーポーズGIF](key-pose-preview.gif)を参照できます。[お茶](tea-preview.gif)、[お辞儀](bow-preview.gif)、[ジャンプ](jump-preview.gif)、[ダンス](dance-preview.gif)は離散キーの確認用です。GIFの380msは診断用の間隔で、作品の演出・発話同期・補間時間ではありません。カップの出入り、通常姿へ戻る腕や眼の切替は、使う場面で設計します。

正確な生成指示と入力の役割・SHAは `provenance/` にあります。生成時の候補・入力snapshot・過去資料は制作原本へ保全し、その履歴パスを画像表示の依存としません。現在使うPNGは登録の `frames[].path` と通常姿から解決できます。採用の根拠は [selection.json](selection.json) と [明示採用台帳](../../../../../../catalogs/character-adoptions-v1.json) に記録します。
