# 素材ライブラリの利用案内

動物・植物・乗り物・昆虫・虹の全120種類を、同じ `current/` から利用できます。全IDの正本は[素材台帳](../../catalogs/asset-library-current-v1.json)です。

## PNGを1枚使う

下表のPNGリンクから、選んだ素材の通常画像を取得して画像として読み込みます。表示するだけならPNG1枚で使えます。Python、動画制作ツール、素材ZIP全体の導入は不要です。ローカルの画像を使う場合は `assets/library/characters/<id>/current/neutral.png` を開いてください。

通常画像は透明背景のPNGです。採用領域をシートから切り出す処理は `current/` の作成時に済んでいるので、そのまま使えます。取込記録にはID・取得元・SHA-256・必要な利用条件を残し、登録座標や出典を参照する場合は同じ素材の `asset.json` も取り込みます。

| ID | 素材 | 用途の目安 | 通常画像 | 登録・取得元 |
|---|---|---|---|---|
| `addax` | アダックス | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/addax/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/addax/current/asset.json) |
| `african-penguin` | ケープペンギン | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/african-penguin/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/african-penguin/current/asset.json) |
| `african-wild-dog` | リカオン | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/african-wild-dog/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/african-wild-dog/current/asset.json) |
| `airplane` | 飛行機 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/airplane/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/airplane/current/asset.json) |
| `akaza-catfish` | アカザ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/akaza-catfish/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/akaza-catfish/current/asset.json) |
| `amami-rabbit` | アマミノクロウサギ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/amami-rabbit/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/amami-rabbit/current/asset.json) |
| `amur-leopard` | アムールヒョウ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/amur-leopard/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/amur-leopard/current/asset.json) |
| `ariake-catfish` | アリアケギバチ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ariake-catfish/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ariake-catfish/current/asset.json) |
| `ariake-striped-loach` | アリアケスジシマドジョウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ariake-striped-loach/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ariake-striped-loach/current/asset.json) |
| `atlantic-puffin` | ニシツノメドリ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/atlantic-puffin/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/atlantic-puffin/current/asset.json) |
| `axolotl` | ウーパールーパー | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/axolotl/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/axolotl/current/asset.json) |
| `band-rumped-storm-petrel` | クロコシジロウミツバメ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/band-rumped-storm-petrel/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/band-rumped-storm-petrel/current/asset.json) |
| `bear-beret` | 赤い帽子のクマ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/bear-beret/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/bear-beret/current/asset.json) |
| `bear-small` | 小さいクマ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/bear-small/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/bear-small/current/asset.json) |
| `black-footed-ferret` | クロアシイタチ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/black-footed-ferret/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/black-footed-ferret/current/asset.json) |
| `black-rhinoceros` | クロサイ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/black-rhinoceros/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/black-rhinoceros/current/asset.json) |
| `black-spider-monkey` | クロクモザル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/black-spider-monkey/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/black-spider-monkey/current/asset.json) |
| `blakiston-fish-owl` | シマフクロウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/blakiston-fish-owl/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/blakiston-fish-owl/current/asset.json) |
| `blue-tree-monitor` | アオホソオオトカゲ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/blue-tree-monitor/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/blue-tree-monitor/current/asset.json) |
| `blue-whale` | シロナガスクジラ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/blue-whale/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/blue-whale/current/asset.json) |
| `bonin-fiddler-crab` | オガサワラベニシオマネキ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/bonin-fiddler-crab/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/bonin-fiddler-crab/current/asset.json) |
| `bornean-orangutan` | ボルネオオランウータン | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/bornean-orangutan/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/bornean-orangutan/current/asset.json) |
| `brent-goose` | コクガン | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/brent-goose/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/brent-goose/current/asset.json) |
| `butterfly` | 蝶 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/butterfly/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/butterfly/current/asset.json) |
| `cat-patches` | 模様のある猫 | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/cat-patches/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/cat-patches/current/asset.json) |
| `chimpanzee` | チンパンジー | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/chimpanzee/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/chimpanzee/current/asset.json) |
| `chinese-alligator` | ヨウスコウワニ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/chinese-alligator/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/chinese-alligator/current/asset.json) |
| `chinese-bleak` | ヒナモロコ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/chinese-bleak/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/chinese-bleak/current/asset.json) |
| `clouded-leopard` | ウンピョウ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/clouded-leopard/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/clouded-leopard/current/asset.json) |
| `cream-companion` | クリーム色の細身の子 | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/cream-companion/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/cream-companion/current/asset.json) |
| `dama-gazelle` | ダマガゼル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/dama-gazelle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/dama-gazelle/current/asset.json) |
| `darwin-fox` | ダーウィンギツネ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/darwin-fox/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/darwin-fox/current/asset.json) |
| `dugong` | ジュゴン | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/dugong/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/dugong/current/asset.json) |
| `eastern-imperial-eagle` | カタシロワシ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/eastern-imperial-eagle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/eastern-imperial-eagle/current/asset.json) |
| `egyptian-tortoise` | エジプトリクガメ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/egyptian-tortoise/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/egyptian-tortoise/current/asset.json) |
| `eskimo-curlew` | エスキモーコシャクシギ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/eskimo-curlew/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/eskimo-curlew/current/asset.json) |
| `ezo-ermine` | エゾオコジョ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ezo-ermine/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ezo-ermine/current/asset.json) |
| `fairy-pitta` | ヤイロチョウ | 鳥の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/fairy-pitta/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/fairy-pitta/current/asset.json) |
| `florida-panther` | フロリダパンサー | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/florida-panther/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/florida-panther/current/asset.json) |
| `flower-bed` | 花壇 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/flower-bed/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/flower-bed/current/asset.json) |
| `gharial` | ガビアル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/gharial/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/gharial/current/asset.json) |
| `giant-otter` | オオカワウソ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/giant-otter/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/giant-otter/current/asset.json) |
| `golden-lion-tamarin` | ゴールデンライオンタマリン | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/golden-lion-tamarin/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/golden-lion-tamarin/current/asset.json) |
| `grass` | 草 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/grass/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/grass/current/asset.json) |
| `great-curassow` | オオホウカンチョウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/great-curassow/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/great-curassow/current/asset.json) |
| `grey-crowned-crane` | ホオジロカンムリヅル | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/grey-crowned-crane/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/grey-crowned-crane/current/asset.json) |
| `hamilton-turtle` | ハミルトンガメ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/hamilton-turtle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/hamilton-turtle/current/asset.json) |
| `hamster` | ハムスター | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/hamster/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/hamster/current/asset.json) |
| `harvest-mouse` | カヤネズミ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/harvest-mouse/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/harvest-mouse/current/asset.json) |
| `hawksbill-turtle` | タイマイ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/hawksbill-turtle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/hawksbill-turtle/current/asset.json) |
| `hedgehog` | ハリネズミ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/hedgehog/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/hedgehog/current/asset.json) |
| `helicopter` | ヘリコプター | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/helicopter/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/helicopter/current/asset.json) |
| `hotoke-loach` | ホトケドジョウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/hotoke-loach/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/hotoke-loach/current/asset.json) |
| `iberian-lynx` | スペインオオヤマネコ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/iberian-lynx/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/iberian-lynx/current/asset.json) |
| `indiana-bat` | インディアナコウモリ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/indiana-bat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/indiana-bat/current/asset.json) |
| `iriomote-cat` | イリオモテヤマネコ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/iriomote-cat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/iriomote-cat/current/asset.json) |
| `ishikawa-frog` | イシカワガエル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ishikawa-frog/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ishikawa-frog/current/asset.json) |
| `japanese-night-heron` | ミゾコイ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/japanese-night-heron/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/japanese-night-heron/current/asset.json) |
| `japanese-rock-ptarmigan` | ニホンライチョウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/japanese-rock-ptarmigan/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/japanese-rock-ptarmigan/current/asset.json) |
| `kakapo` | カカポ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/kakapo/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/kakapo/current/asset.json) |
| `kangaroo` | カンガルー | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/kangaroo/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/kangaroo/current/asset.json) |
| `kazetoge-bitterling` | カゼトゲタナゴ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/kazetoge-bitterling/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/kazetoge-bitterling/current/asset.json) |
| `koala` | コアラ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/koala/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/koala/current/asset.json) |
| `komodo-dragon` | コモドドラゴン | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/komodo-dragon/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/komodo-dragon/current/asset.json) |
| `ladybug` | てんとう虫 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ladybug/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ladybug/current/asset.json) |
| `leatherback-turtle` | オサガメ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/leatherback-turtle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/leatherback-turtle/current/asset.json) |
| `little-bird` | 小鳥 | 鳥の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/little-bird/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/little-bird/current/asset.json) |
| `malayan-tapir` | マレーバク | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/malayan-tapir/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/malayan-tapir/current/asset.json) |
| `meerkat` | ミーアキャット | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/meerkat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/meerkat/current/asset.json) |
| `miyako-grass-lizard` | ミヤコカナヘビ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/miyako-grass-lizard/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/miyako-grass-lizard/current/asset.json) |
| `mole` | モグラ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/mole/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/mole/current/asset.json) |
| `moose` | ヘラジカ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/moose/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/moose/current/asset.json) |
| `new-england-cottontail` | ニューイングランド ワタオウサギ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/new-england-cottontail/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/new-england-cottontail/current/asset.json) |
| `northern-bald-ibis` | ホオアカトキ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/northern-bald-ibis/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/northern-bald-ibis/current/asset.json) |
| `northern-hairy-nosed-wombat` | キタケバナウォンバット | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/northern-hairy-nosed-wombat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/northern-hairy-nosed-wombat/current/asset.json) |
| `okapi` | オカピ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/okapi/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/okapi/current/asset.json) |
| `okinawa-rail` | ヤンバルクイナ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/okinawa-rail/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/okinawa-rail/current/asset.json) |
| `okinawa-spiny-rat` | オキナワトゲネズミ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/okinawa-spiny-rat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/okinawa-spiny-rat/current/asset.json) |
| `onagadori` | オナガドリ | 鳥の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/onagadori/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/onagadori/current/asset.json) |
| `oriental-stork` | コウノトリ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/oriental-stork/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/oriental-stork/current/asset.json) |
| `otton-frog` | オットンガエル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/otton-frog/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/otton-frog/current/asset.json) |
| `pallas-cat` | マヌルネコ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/pallas-cat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/pallas-cat/current/asset.json) |
| `philippine-eagle` | フィリピンワシ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/philippine-eagle/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/philippine-eagle/current/asset.json) |
| `pika` | ナキウサギ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/pika/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/pika/current/asset.json) |
| `piping-plover` | フエコチドリ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/piping-plover/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/piping-plover/current/asset.json) |
| `polar-bear` | ホッキョクグマ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/polar-bear/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/polar-bear/current/asset.json) |
| `proboscis-monkey` | テングザル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/proboscis-monkey/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/proboscis-monkey/current/asset.json) |
| `przewalski-horse` | モウコノウマ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/przewalski-horse/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/przewalski-horse/current/asset.json) |
| `pygmy-hippopotamus` | コビトカバ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/pygmy-hippopotamus/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/pygmy-hippopotamus/current/asset.json) |
| `quokka` | クアッカーワラビー | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/quokka/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/quokka/current/asset.json) |
| `rabbit-beret` | ピンクのウサギ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/rabbit-beret/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/rabbit-beret/current/asset.json) |
| `rabbit-flower` | 花付きウサギ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/rabbit-flower/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/rabbit-flower/current/asset.json) |
| `rainbow` | 虹 | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/rainbow/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/rainbow/current/asset.json) |
| `red-crowned-crane` | タンチョウヅル | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/red-crowned-crane/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/red-crowned-crane/current/asset.json) |
| `red-panda` | レッサーパンダ | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/red-panda/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/red-panda/current/asset.json) |
| `red-wolf` | アカオオカミ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/red-wolf/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/red-wolf/current/asset.json) |
| `reticulated-giraffe` | アミメキリン | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/reticulated-giraffe/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/reticulated-giraffe/current/asset.json) |
| `ring-tailed-lemur` | ワオキツネザル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ring-tailed-lemur/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ring-tailed-lemur/current/asset.json) |
| `rocket` | ロケット | 背景ギミック | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/rocket/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/rocket/current/asset.json) |
| `ruddy-breasted-crake` | ヒクイナ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/ruddy-breasted-crake/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/ruddy-breasted-crake/current/asset.json) |
| `sakhalin-taimen` | イトウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/sakhalin-taimen/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/sakhalin-taimen/current/asset.json) |
| `sand-tiger-shark` | シロワニ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/sand-tiger-shark/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/sand-tiger-shark/current/asset.json) |
| `sea-otter` | ラッコ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/sea-otter/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/sea-otter/current/asset.json) |
| `seboshitabira-bitterling` | セボシタビラ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/seboshitabira-bitterling/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/seboshitabira-bitterling/current/asset.json) |
| `setouchi-salamander` | セトウチサンショウウオ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/setouchi-salamander/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/setouchi-salamander/current/asset.json) |
| `shoebill` | ハシビロコウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/shoebill/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/shoebill/current/asset.json) |
| `short-tailed-albatross` | アホウドリ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/short-tailed-albatross/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/short-tailed-albatross/current/asset.json) |
| `siamese-cat` | シャム猫 | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/siamese-cat/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/siamese-cat/current/asset.json) |
| `siberian-crane` | ソデグロヅル | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/siberian-crane/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/siberian-crane/current/asset.json) |
| `southern-bluefin-tuna` | ミナミマグロ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/southern-bluefin-tuna/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/southern-bluefin-tuna/current/asset.json) |
| `southern-ground-hornbill` | ミナミジサイチョウ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/southern-ground-hornbill/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/southern-ground-hornbill/current/asset.json) |
| `spoon-billed-sandpiper` | ヘラシギ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/spoon-billed-sandpiper/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/spoon-billed-sandpiper/current/asset.json) |
| `steller-sea-lion` | トド | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/steller-sea-lion/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/steller-sea-lion/current/asset.json) |
| `sumatran-elephant` | スマトラゾウ | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/sumatran-elephant/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/sumatran-elephant/current/asset.json) |
| `tasmanian-devil` | タスマニアデビル | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/tasmanian-devil/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/tasmanian-devil/current/asset.json) |
| `tora` | とら | キャラクター | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/tora/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/tora/current/asset.json) |
| `tree-kangaroo` | キノボリカンガルー | 擬人化キャラ | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/tree-kangaroo/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/tree-kangaroo/current/asset.json) |
| `vaquita` | コガシラネズミイルカ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/vaquita/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/vaquita/current/asset.json) |
| `yellow-breasted-bunting` | シマアオジ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/yellow-breasted-bunting/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/yellow-breasted-bunting/current/asset.json) |
| `zebra-garden-eel` | ゼブラアナゴ | 動物の小物 | [PNG](https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/zebra-garden-eel/current/neutral.png) | [asset.json](https://raw.githubusercontent.com/anoneunknowns/youtube/main/assets/library/characters/zebra-garden-eel/current/asset.json) |

表の画像・JSONはGitHubの `main` にある配布版です。再現する参照を固定する場合は、両URLの `main` を同じコミットIDへ置き換えます。JSONとPNGは同じ参照から取得し、受け取った画像のSHA-256をJSONの値と照合してください。

画像本体を直接取得する例です。保存名は取り込み先に合わせて指定します。

```sh
curl --fail --location "https://media.githubusercontent.com/media/anoneunknowns/youtube/main/assets/library/characters/rabbit-beret/current/neutral.png" --output rabbit-beret-neutral.png
```

## キャラと小物の表現・使い方

動物の表現は、シャム猫・ハリネズミ・トラのような軽い擬人化と、ヤイロチョウのような丸く簡略化した小物の2パターンを基準にします。ハムスターと黄色い小鳥は例外的な既存デザインです。制作の基準は[画風と同一性](../../docs/IMAGE-ASSET-MANAGEMENT.md#画風と同一性)を参照してください。

`style_pattern` がある素材では、`slightly-anthropomorphic-character` が腕・短い二足立ち・人らしい表情を持つキャラ、`bird-like-prop` が鳥や水生動物等の小物です。`usage_role` は `cast-character` / `background-animal-prop` を示します。どちらも通常PNGの取得手順は同じです。未記載の素材は、採用通常姿と登録済みの用途を基準に扱います。

通常姿だけの素材は `poses`・`clips` が空でも利用できます。動きを推測して別名画像を作ったり、ポーズのないIDへ他の動物の登録を流用したりしません。小物の推奨表示幅・身体基準高は素材ごとに違います。`asset.json` の `source_index.path` が指す[採用台帳](../../catalogs/character-library-v1.json)で同じIDを探します。`characters[].neutral.source_manifest` がある素材はその原画記録を参照し、`resolution_review` が存在する場合は表示条件も確認します。未記載の確認項目は原画記録や台帳の `source_collections` から登録・QAを辿り、ポーズは `asset.json` の `source_registrations` も参照します。身体基準・支点は選んだ `current/` のレコードを使い、長い尾・角・嘴・鰭の全体bboxへ毎回fitし直さないでください。[原画・採用確認の記録](collections/animal-species-stock/v001/README.md)には、通常姿の作成条件と確認範囲をまとめています。

## 共通フォルダとJSONの読み方

全IDが同じ構造を持ちます。利用できるポーズや動作は素材ごとに異なるため、ファイル名を推測せず `asset.json` のキーを選びます。

```text
assets/library/characters/<id>/current/
  asset.json
  neutral.png
  poses/<namespace>/<pose>.png
  clips.json
  icons/<name>.png（対応する素材のみ）
```

| JSONの項目 | 内容・パスの基準 |
|---|---|
| 素材台帳の `assets[].manifest` | プロジェクトルートから各 `current/asset.json` へ進む |
| `asset.json` の `neutral.path` | `asset.json` のある `current/` から通常PNGを解決する |
| `asset.json` の `poses[キー].path` | 同じ `current/` から選んだポーズPNGを解決する |
| `asset.json` の `icons[名前].path` | 同じ `current/` から頭部等の独立アイコンを解決する |
| `asset.json` の `clips.path` | 同じ `current/` から `clips.json` を解決する |
| `source_path`、`source_index.path`、`source_registrations[].path` | プロジェクトルートを基準とする取得元・登録の記録 |
| `sha256` | 対応するファイルのSHA-256。`source_sha256` は元ファイルの値 |

`neutral.png` は採用原画のバイト一致コピー、または指定されたシート領域の無損失切り出しです。切り出したPNGと元シートではSHAが異なり得るため、利用PNGはそのレコードの `sha256` と比較します。元シートの `source_sha256` と混同しません。

通常姿・ポーズの選択はINDEXの `source_collections` にある検査済みcollectionと、[明示採用台帳](../../catalogs/character-adoptions-v1.json)から辿れます。画像利用では `current/` を入口とし、原画から一覧を再構築する場合はこの採用記録と根拠を読みます。版番号や過去の画風QAから現行版を推測しません。

PowerShellで、通常PNGだけを照合する例です。画像表示に検証ツールの実行を必須とはしません。

```powershell
$base = "assets/library/characters/rabbit-beret/current"
$asset = Get-Content "$base/asset.json" -Raw | ConvertFrom-Json
$png = Join-Path $base $asset.neutral.path
$actual = (Get-FileHash -Algorithm SHA256 $png).Hash.ToLowerInvariant()
if ($actual -ne $asset.neutral.sha256) { throw "PNGのSHA-256が登録値と一致しません" }
```

## ポーズや動作を使う

`asset.json` の `poses` から画像と登録座標を選びます。名前空間は機能を識別する互換IDで、制作時期を示す区分ではありません。

| 名前空間 | 機能 | キーの例 |
|---|---|---|
| `basic/` | 基本の表情・しぐさ | `basic/blink` |
| `expanded/` | 手振り・視線・姿勢などの表情と全身動作 | `expanded/wave_low` |
| `eyecatch/` | 紅茶・おじぎ・ジャンプ・ダンス等の短い演出 | `eyecatch/tea_sip` |
| `gimmick/` | 植物・乗り物・昆虫・虹の動作 | `gimmick/fully_open` |
| `app/` | タップ・回答リアクション・待機・池ジャンプ | `app/success_air` |

表はキーの例です。必要なキーがその素材の `poses` にあることを確認してください。通常姿は `neutral` のレコードを使い、各名前空間にある `neutral` というポーズへ自動的に置き換えません。

クマの通常姿と短い演出18状態は、1254×1254の透過原画を共通の身体基準高1107pxで登録しています。通常姿に相当する3状態は同じ原画の再利用です。画像は他の素材と同様に `current/` から選べます。[ポーズ一覧](characters/bear-beret/eyecatches/v003/pose-review.png)と[採用・品質の記録](characters/bear-beret/eyecatches/v003/README.md)も参照できます。

`clips.json` の `clips` は、名前付きの動作定義です。各 `frames` の値を `asset.json` の `poses` へ対応付け、`durations_ms` と `loop` が記録されている場合はそれを読みます。`timing` に時間未指定とある動作は、使う場面で時間を設計・確認してください。移動や `procedural_effect` がある場合は、その指定も合わせて再生します。虹は同じPNGを使い、出現・透明度・光の移動を再生時に変えます。

動作の確認入口は各 `asset.json` の `source_registrations` と、その登録が示すプレビューです。クマの短い演出は[姿勢一覧](characters/bear-beret/eyecatches/v003/pose-review.png)と[キーポーズGIF](characters/bear-beret/eyecatches/v003/key-pose-preview.gif)で確認できます。[基本の表情・しぐさ](collections/animal-motions/v001/index.html)、[全身のしぐさ](collections/character-expansion/v001/index.html)、[配置用素材の動作GIF](collections/background-gimmicks/v001/index.html)も参照できます。全120種類のポーズと動作の有無は共通台帳と各 `asset.json`・`clips.json` を正本にし、過去のcollectionの一覧から現行の採用先を推測しません。

### タップ・回答・待機・池ジャンプ

赤いベレー帽のクマ、小さいクマ、ハムスター、花飾りのウサギ、クリーム色の細身の子、ぶち猫は、`app/` の反応と待機を同じ `current/asset.json` から利用できます。12反応は `blink,tap_down,tap_pop,think,aha,success_ready,success_air,success_land,oops,retry,cheer,signature`、待機は `idle_rest,idle_stretch,idle_nap` です。

池は2体のクマに `pond_stand_right,pond_air_right,pond_land_right,pond_air_left,pond_stand_left,pond_land_left` を収録します。空中の支点は描かれた足の解剖上の位置です。アプリ側で放物線を与え、画像の余白から推定した浮きを二重に足しません。クマの `seated_tap_down,seated_tap_pop,seated_blink` は、タイトル画面の座位から立位へ急に切り替えず反応させるための姿勢です。

`scene_relative_scale` は赤いベレー帽のクマに対する場面上の身体高比の設定値です。基準表示高にこの比を掛け、それを各PNGの `reference_height_px` で割って描画倍率を求めます。小さいクマ0.65、ハムスター0.30、花飾りのウサギ1.05、クリーム色の子とぶち猫0.95です。元のクマの基準高1107pxは帽子を含む従来の登録を維持し、各シートの校正で対応付けています。見かけの全高だけから比率を再計算したり、姿勢ごとの外接高さへfitし直したりしないでください。

ハムスターは手足のない体底支点、花飾りのウサギは固有の花、ぶち猫は身体側に固定した模様、クリーム色の子は種別未確定の細身の姿を保ちます。顔アイコンはクマの `icons.face` から取得し、身体基準高を持つ全身PNGと区別します。

1008×567での明暗・原寸・離散キーポーズの素材QAは、[確認記録](collections/app-character-stock/v001/README.md)を参照してください。実アプリへの組込み後の補間、速度、画面遷移は利用側で確認します。

<a id="背景素材8種類の表示と動作"></a>
## 支点・共通尺度・表示サイズ

画像を配置・拡大する場合は、選んだ画像の `anchor_px` と `reference_height_px` を使います。支点は足元・根元・基部・胴体中心などで、意味は `anchor_kind` や取得元の登録に従います。透明なキャンバス全体の中心や、翼・尾・炎を含めた外接矩形の中心を支点の代わりにしません。

```text
scale = desired_reference_height / reference_height_px
draw_x = target_anchor_x - anchor_px[0] * scale
draw_y = target_anchor_y - anchor_px[1] * scale
```

同じ校正済みシートの動作には共通の等方縮尺を使います。シートをまたぐ場合も登録済みの基準を使い、しゃがみ・翼の開閉・炎の長さ・ローターの位相・虹の部分表示ごとに個別fitしません。`--height` 等が表す基準高と、見かけの幅は別の量です。

| 素材・動作 | 原寸QAで確認した表示の目安 |
|---|---|
| 草 | 通常姿の幅600pxを基準。揺れ途中の広がりは別に余白を確保 |
| 花壇 | 通常姿の幅520pxを基準。花や葉の揺れも枠内へ収める |
| 飛行機 | 水平姿勢の全幅360px |
| ロケット | 炎を除いた胴体高300px。炎を含む全範囲の余白を確保 |
| ヘリコプター | 主ローターの非短縮時の展開幅500px。位相で機体を拡大しない |
| 蝶 | 翼全開時の幅200px。中心支点と胴体基準を使用 |
| てんとう虫 | 脚・飛行翼を除く甲羅幅140px。展開した翼は別に余白を確保 |
| 虹 | 完全形の全幅1200px。出現途中も同じ基部・縮尺を維持 |

表示条件の根拠は各登録とQAを参照します。オナガドリは身体で縮尺を決め、尾の全幅を収めます。`peck_half`・`peck_down` は下向きのしぐさで、地面への実接触を保証しません。空中姿勢は登録された支点種別を読み、原画に含まれる浮きを二重に加えません。紅茶の動作はカップを持つループなので、通常姿との接続ではカップの出入りを設計します。

GIFは素材の動作確認用です。利用する画面で最大表示の精細さ、両軸の配置、切れ、体格・支点の跳ね、ループ、字幕や教材との余白を確認します。素材のSHA整合、画風の指摘、完成作品の動作検査はそれぞれ別の記録として扱います。[画風の確認資料](collections/character-style-audit/v001/index.html)にある修正候補も、利用する素材について確認してください。

<a id="取得検証"></a>
## Git LFSで画像を取得する

PNGを直接取得するほか、Gitでライブラリを取得する場合はGit LFSを使います。LFSポインタは画像本体ではありません。内容が `version https://git-lfs.github.com/spec/v1` から始まるテキストなら、LFSの実体を取得してください。

初回cloneで画像の自動一括取得を止めるPowerShell例です。

```powershell
git lfs install
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://github.com/anoneunknowns/youtube.git num-num-assets
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
Set-Location num-num-assets
```

通常PNGだけなら、次の対象に絞れます。JSONは通常のGitファイルとしてcloneに含まれます。この取得状態では、未取得のポーズ等まで要求する全体検証は実行しません。

```powershell
git lfs pull --include="assets/library/characters/*/current/neutral.png" --exclude=""
```

ポーズ・確認GIF・登録元の画像を含むライブラリ全体が必要な場合は、対象を広げます。下記に音声・動画・モデルの取得は含みません。フォントは一覧画像の検証・再構築に使います。

```powershell
git lfs pull --include="assets/library/characters/**,assets/library/collections/**,assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf" --exclude=""
```

## ライブラリの検証とZIP

全画像を取得した環境では、依存を導入してライブラリを検証できます。これは画像を1枚表示する場合の必須工程ではありません。

```powershell
python -m pip install -r requirements.txt
python tools/character_library.py verify
python tools/unified_asset_library.py verify
```

ポーズのプレビューを描画する場合、`character_library.py` の `basic/` 相当の指定は接頭辞なし、他の名前空間はそのまま渡します。例のポーズが対象IDに登録されていることを確認して使います。

```powershell
python tools/character_library.py preview --character siamese-cat --pose expanded/wave_low --height 430 --output ../cat-wave.png
python tools/character_library.py preview --character butterfly --pose gimmick/fully_open --height 77 --output ../butterfly.png
```

配布するライブラリ一式は、公開用checkoutのルートから未使用の出力先へZIPを作ります。profileのない制作原本から同じexportを実行すると、ローカル在庫の候補・履歴も含む別の保存範囲になるため、配布用ZIPと区別してください。

```powershell
python tools/character_library.py export --output ../num-num-asset-library.zip
```

ZIPには `character-library/` を起点に、選択された全120素材の通常画像・ポーズ・動作定義・共通台帳・登録・生成条件・確認資料・検証ツールを収録し、`.sha256` と `.json` の検証記録も出力します。展開後はその `character-library/` へ移動して必要な依存を導入し、`character_library.py verify` と `unified_asset_library.py verify` を実行します。画像・JSONの相対配置を維持してください。

通常の利用では `current/` や期待SHAを編集しません。採用管理担当が登録を更新した後に `unified_asset_library.py build` で共通入口を作り直し、`verify` で元画素・座標・参照を照合します。取り込み先での検証エラーは、取得漏れ・ポインタ・参照先・実体を調べて解決し、`refresh` で期待ハッシュを上書きして隠しません。

## リメイク候補を選ぶ

前バージョンとリメイク案を見比べるときは、[画像の比較・選択ツール](../../docs/IMAGE-ASSET-MANAGEMENT.md#リメイク候補をユーザーに提示する)を使えます。「前バージョン」「AIおすすめ」の印を見ながら、採用したい案・前バージョンの維持・保留を選べます。選択結果は履歴として保存し、ほかの画像でも同じ仕組みを利用できます。

修正が必要な画像だけ新規案を作り、同一尺度の原寸・明暗・前後姿勢で比較します。明確な改善があり、同一性や画風等に退行がない場合だけ差し替え、同程度・判断不明なら既存を維持します。

[仕上がりの再検査記録](collections/asset-polish-review/v001/README.md)には、現行画像のSHA・観測尺度・確認範囲と、鮮明さが増しても画調のつながりを優先して既存版を維持した比較判断をまとめています。

[正式版の全数原寸再検査](collections/final-image-review/v001/README.md)には、全画像の確認範囲と、細部に不足があった2姿勢だけを新規原画へ差し替えた判断をまとめています。利用画像はすべて同じ `current/` に反映し、通常姿を含む良好な素材を保持します。

## 保存範囲と利用条件

GitHubで配布する範囲は[公開対象一覧](https://github.com/anoneunknowns/youtube/blob/main/catalogs/github-publication-v1.json)の `files`、公開用checkoutから作る素材パッケージの範囲は `character_library_files` が正本です。HTTPで取得する画像とJSONは同じGitHub参照から、ローカル画像とJSONは同じcheckoutの `current/` から組にして使います。公開用の全データを取得したcheckoutは `python tools/verify_github_publication.py` で確認できます。

制作原本では現在の利用・再制作・必要なQAに使う原画・入力・比較資料を保管します。不要な旧媒体を一律に保管し続ける方針ではありません。整理の優先度は[削除手順](../../docs/IMAGE-ASSET-MANAGEMENT.md#不要旧版を削除する場合)、当時のパス・SHAと現在の提供状況は[管理設定](../../catalogs/character-asset-management-v1.json)の `retirement_records` から確認します。公開対象にない候補・未使用の版・動画は、記録にパスやSHAが残っていても配布ファイルを意味しません。`verify_workspace.py`、`manage_character_assets.py check`、`update_production_archive.py --check` は、必要な保管資料や動画も揃えた制作原本向けの管理検査です。画像利用や公開範囲の確認とは分けます。公開側へ同期する手順は [GitHub公開仕様](https://github.com/anoneunknowns/youtube/blob/main/docs/GITHUB-PUBLICATION.md) に従います。

現在の利用・再制作・必要なQAに使う元原画や生成シートを保持し、正確なプロンプト・入力の役割とSHA・登録・過去の検査記録は、媒体の提供状況と分けて管理します。管理の詳細は[画像管理仕様](../../docs/IMAGE-ASSET-MANAGEMENT.md)、担当・品質は[画像管理一覧](character-assets.html)と[管理設定](../../catalogs/character-asset-management-v1.json)を参照してください。版番号の最大値、更新日時、管理在庫への収録だけで採用や画風合格を推定しません。

各素材の取得元・生成条件・依存物の利用条件を確認し、必要な条件を画像と取込記録に添えてください。この案内から一律の再配布ライセンスを推定しません。履歴の絶対パスや元生成先は作成時の記録であり、現在のPCの読み込み先には使いません。
