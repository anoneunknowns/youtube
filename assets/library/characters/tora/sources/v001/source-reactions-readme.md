# キャラクター反応画像 v2

全8キャラ × 12ポーズ = 96差分の透過PNG。組み込み `image_gen` で原画を参照して新規生成しました。1キャラ1枚のアトラスで、4列×3行です。

[画像・動きのプレビュー](../../../design/character-reactions-v2/gallery.html) / [演出設計](../../../design/character-reactions-v2/README.md) / [カタログ](catalog.json) / [計測結果](verification.json) / [20種類の演出データ](choreography.json) / [送信した生成プロンプト](prompts.md)

逆立ち・紅茶・ごろ寝など、将来用の遊びポーズ48差分は[playful-v1](../playful-v1/README.md)へ追加しました。操作・正誤用のこの96ポーズとは別の素材群です。

| キャラ | 画像 | 固有のしぐさ |
| --- | --- | --- |
| 赤いベレー帽のくま | [bear-beret-reactions.png](bear-beret-reactions.png) | 帽子が片目にかかる |
| 一回り小さいくま | [bear-small-reactions.png](bear-small-reactions.png) | 背伸びして少しぐらつく |
| ハムスター | [hamster-reactions.png](hamster-reactions.png) | 片耳がぺこりと倒れる |
| 花飾りのうさぎ | [rabbit-flower-reactions.png](rabbit-flower-reactions.png) | 長い耳がふわりと倒れる |
| ことり | [bird-reactions.png](bird-reactions.png) | 自分のしっぽを振り返る |
| とら | [tora-reactions.png](tora-reactions.png) | くるんとしたしっぽを見る |
| 白い細身の子 | [cream-companion-reactions.png](cream-companion-reactions.png) | ばねのように横へしなる |
| 模様のある猫 | [cat-patches-reactions.png](cat-patches-reactions.png) | 自分のしっぽの横からのぞく |

各シートの順番は `blink / tap_down / tap_pop / think / aha / success_ready / success_air / success_land / oops / retry / cheer / signature`。実際のピクセル領域はカタログを使います。セルのキャンバス寸法や絵の余白を、キャラ間の身長差として使いません。

帽子なしのくまは、帽子のくまより一回り小さいというユーザー指定を保持します。従来の身長比0.65は表示用の暫定値であり、厳密な比率まで承認済みとは扱いません。原画の中立姿勢から縮尺を一度決め、全ポーズを同じ縮尺で表示します。各絵をセルいっぱいに伸ばしません。

全キャラの頬に赤みを追加せず、ハムスターには手足・別の胴を作らず、ことりは点目とシンプルな輪郭を保ち、猫の左右の模様を維持しています。生成画像の端にある極低alphaの色は、保存時に加工していません。透過計測の閾値と実測は検証記録で区別します。

画像差分をゲームの入力・正誤と結び付ける本編への組み込みは、今回の画像生成には含めていません。旧48ポーズ、採用中の基準絵、本編コード、Windows/Androidのビルドはそのままです。カタログのセル指定は切り出し用で、滑らかな動きに必要なポーズ間の基準点合わせは採用時に確認します。

