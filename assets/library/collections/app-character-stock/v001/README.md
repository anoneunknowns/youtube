# アプリ用の反応・待機・池ジャンプ・顔アイコン

素材の利用入口は[全素材の共通ガイド](../../../README.md)と[共通台帳](../../../../../catalogs/asset-library-current-v1.json)です。以下の6体も同じ `current/neutral.png`・`asset.json`・`poses`・`clips.json` から利用できます。収録時期で使い方を分けません。

| ID | 名前 | `app/`の状態数 | 通常姿 | JSON |
|---|---|---:|---|---|
| `bear-beret` | 赤いベレー帽のクマ | 27 | [PNG](../../../characters/bear-beret/current/neutral.png) | [登録](../../../characters/bear-beret/current/asset.json)・[動作](../../../characters/bear-beret/current/clips.json) |
| `bear-small` | 小さいクマ | 22 | [PNG](../../../characters/bear-small/current/neutral.png) | [登録](../../../characters/bear-small/current/asset.json)・[動作](../../../characters/bear-small/current/clips.json) |
| `hamster` | ハムスター | 16 | [PNG](../../../characters/hamster/current/neutral.png) | [登録](../../../characters/hamster/current/asset.json)・[動作](../../../characters/hamster/current/clips.json) |
| `rabbit-flower` | 花付きウサギ | 16 | [PNG](../../../characters/rabbit-flower/current/neutral.png) | [登録](../../../characters/rabbit-flower/current/asset.json)・[動作](../../../characters/rabbit-flower/current/clips.json) |
| `cream-companion` | クリーム色の細身の子 | 16 | [PNG](../../../characters/cream-companion/current/neutral.png) | [登録](../../../characters/cream-companion/current/asset.json)・[動作](../../../characters/cream-companion/current/clips.json) |
| `cat-patches` | 模様のある猫 | 16 | [PNG](../../../characters/cat-patches/current/neutral.png) | [登録](../../../characters/cat-patches/current/asset.json)・[動作](../../../characters/cat-patches/current/clips.json) |

新規描画の採用は113点（全身・姿勢112点と顔アイコン1点）です。上表は動作定義から通常姿へ戻るための `app/neutral` 別名も数えます。同じPNGの別名と新規原画の点数を区別してください。赤いベレー帽のクマの通常姿、従来の良好なポーズ、他素材、作品の採用入力は維持しています。

反応12種は `blink,tap_down,tap_pop,think,aha,success_ready,success_air,success_land,oops,retry,cheer,signature`、待機3種は `idle_rest,idle_stretch,idle_nap`。池の2体には往復に使う待機・空中・着地を、赤いベレー帽のクマには座位のタップ・瞬きを収録します。各IDの正確なキーは `asset.json` を読んでください。顔はクマの `icons.face` です。

左右の `pond_preload_left`・`pond_preload_right` は三腕に見える崩れが再監査で見つかったため、腕2本の新規原画へ明示的に差し替えました。[比較・採用根拠](../../../characters/bear-beret/generation-batches/preload-anatomy-fix-20261113-v001/selection.json)を確認できます。通常姿・他の良好なポーズと動作列は保持しています。

## 基準と使い方

各PNGは透過RGBAで、原画の指定セルを無損失で切り出しています。元出力、実寸、抽出矩形、正確なプロンプト、直接入力の役割とSHA、PNGのSHA、支点、シート共通の基準高を登録から辿れます。生成は組込みimagegenで行い、色抜き・アルファ清掃・輪郭の機械的な細線化はしていません。

`scene_relative_scale` は算数アプリから引き継ぐ場面設定（小クマ0.65、ハムスター0.30、花ウサギ1.05、クリーム色の子とぶち猫0.95）で、原画の `reference_height_px` とは別です。元のクマの基準1107pxと通常姿のSHAは保持し、他シートは頭・身体の共通尺度から校正します。ポーズごとの外接高さに合わせ直しません。

池の空中姿勢は解剖上の描かれた足を支点にします。アプリ側が放物線を与え、セル内の透明余白や過去画像の浮きを二重に加えません。ハムスターは手足を追加しない体底支点です。顔アイコンへ全身の身体基準や足支点を与えません。

## 品質確認と選択

Issue [#1](https://github.com/anoneunknowns/youtube/issues/1)・[#2](https://github.com/anoneunknowns/youtube/issues/2)とユーザーの制作・管理の委任に基づくAIの採用判断です。ユーザー自身のクリックとして記録していません。

1008×567相当の明暗、原寸、通常姿から成功、待機から操作反応、池の往復を離散キーポーズで確認しました。各batchの `qa-review.json` が対象SHA・支点・校正・実効解像度・配置結果を記録しています。[別担当の確認](independent-review.json)、[比較画像の対応表](review-image-map.json)、[管理担当の目視](root-static-review.json)も併記します。

花飾りは再監査で、参照と全16姿勢とも5弁と確認しました。以前の「6弁へ変化」という検査記録は数え間違いでした。当時のQA JSONを保全し、[再監査と訂正](../../../characters/bear-beret/generation-batches/preload-anatomy-fix-20261113-v001/README.md)へ新しい観測を記録しています。猫の身体側の模様、クリーム色の子の細身の姿、小クマの頬に赤を足さない条件も確認しています。

初回の配置不合格や背景が混入した池の試作を、合格記録へ書き換えていません。採用版の表示検査はSOURCEの両軸0.5pxを維持し、縮小時のラスタ位相は原画・登録座標を変えずにプレビュー側だけで校正します。校正を固定した後の実素材の移動負例でも誤合格を検査しました。不採用画像と用済みの旧プレビュー画像は公開一覧に含めず、判断・失敗のJSON記録を保全しています。

素材の離散キー確認であり、算数アプリへの組込み後の補間・速度・完成画面の連続動作を検査済みとは扱いません。クリップの時間・ループ・空中の移動方式を読み、利用画面で最大表示・接続・教材との余白を確認してください。
