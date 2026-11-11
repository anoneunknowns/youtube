# ベース画像の生成記録

生成日：2026-11-02（日本時間）。生成方法：組み込み image_gen。参照画像を使った生成・編集、透過背景を指定。外部CLI/APIへの切替は行っていません。

以下は各採用画像に用いた最終プロンプトです。とらは当初の作業名が cat/tabby でしたが、ユーザーの呼称に合わせて整理しています。くま・うさぎは初稿から頬の赤みを取り除く編集を行いました。

## 赤い帽子のくま

ファイル：`bear-beret.png`

```text
Use case: precise-object-edit, identity-preserve. Edit target is reference1 standalone yellow bear with red beret. Reference2 is the user's ORIGINAL drawing and is authoritative for its character identity. Make ONE specific change to reference1: REMOVE ALL PINK/RED CHEEK BLUSH AND THE THREE PINK CHEEK STROKES on both cheeks. Restore those areas to the same pale buttery yellow fur and watercolor texture as the surrounding face. The standard neutral base MUST have no pink or red cheeks, no blush lines, no cheek circles, no makeup. Keep the red beret, pink tongue, oval brown eyes, original distinctive arched muzzle outline, smile, exact silhouette, full-body standing neutral pose, proportions, line quality, paint texture, palette, centered composition and all other features exactly unchanged. Do not redesign or genericize this original character. Preserve genuine transparent alpha background and comfortable margins. Exactly ONE isolated character, no labels/props/scene/shadow. Match original bear's face; do not borrow any other company's mascot design.
```

## 小さいくま

ファイル：`bear-small.png`

```text
Use case: identity-preserve, background-extraction. Create ONE canonical full-body base sprite of the SMALL CREAM BEAR from reference1 LEFT seated with the blue ball and reference2 LEFT holding the blue fruit bowl. These are original drawings supplied by the owner. This is a DISTINCT smaller bear character, NOT the large yellow red-beret bear in the same scenes and NOT the tiny legless hamster on the right in reference2. Identify the correct small cream bear: light ivory/cream fur, two rounded ears, round head, elongated oval dark-brown eyes with narrow white highlights, tiny dark-brown nose, the same unusual dark-brown outer arched muzzle line around a small cheerful open mouth with a little pink tongue, plump compact body, short rounded arms and legs, small round bear tail. No red hat and no accessories or clothes. Preserve these particular original facial features/proportions; don't replace with generic teddy-bear facial features or another company's mascot. Reference3 is an art-finish reference only: similar warm brown outlines and gentle watercolor texture; do NOT take its yellow fur or red hat. Pose: whole body standing nearly front-on, both paws relaxed at its sides slightly away from torso, feet planted and entirely visible, natural calm friendly expression, no held objects. Standard base has NO pink/red cheek blush, NO diagonal cheek lines, NO cheek circles or makeup; cheeks the exact same cream as face. Square composition with about10percent clear margins, centered, whole character occupies about78percent imageheight. GENUINELY TRANSPARENT alpha background, no white/colored background, no checkerboard painted in, no scene, floor, cast shadow, white sticker outline, labels, name, extra poses, other characters or props. Exactly one complete original small cream bear base.
```

## ハムスター

ファイル：`hamster.png`

```text
Use case: identity-preserve, background-extraction. Create exactly ONE isolated canonical base image of the user's original CREAM HAMSTER visible at the far RIGHT on the yellow book in reference1, and LEFT beside the wooden tool tray in reference2. These two originals define the design; reference3 is art finish only. This hamster is a DISTINCT character, not the small full-bodied bear on the LEFT of reference1, not the large redhat bear. Faithfully preserve the unusual original hamster design: a very small simple warm-ivory/cream squat rounded bean or soft triangular dumpling silhouette, wide round base narrowing gently toward the upper head, two small round ears merged into the top corners, two tiny dark-brown vertical oval/dot eyes, and its distinctive short dark-brown round double-arch 'm'-shaped mouth directly underneath, exactly as in source. Single continuous head-and-body blob, NO separate neck or torso, no invented visible limbs or tail, no whiskers, no pink nose, no teeth or realistic hamster cheek pouches. No red/pink cheek blush, cheek lines, cheek circles, or makeup: face and cheeks all plain same cream fur. Front-facing, centered, quietly resting in neutral standard pose, no held objects, no expressions added; keep its characteristic m mouth. Match reference3's warm brown softly textured handdrawn outline and gentle watercolor filled finish while preserving the original simple form, not any company's famous mascot. One square transparent sprite, generous even margins, whole creature occupies about65percent canvaswidth and48percent canvasheight because it is a squat character. GENUINELY TRANSPARENT ALPHA background, no colored/white background or drawn checkerboard; no floor, cast shadow, white sticker contour, text, props, setting, other characters, duplicate views or labels.
```

## 花飾りのうさぎ

ファイル：`rabbit-flower.png`

```text
Use case: precise-object-edit, identity-preserve. Edit target reference1 standalone pink flower rabbit. Reference2 is the user's original character illustration. Change ONLY the following: REMOVE ALL darker pink/red CHEEK BLUSH and the THREE DIAGONAL CHEEK STROKES on both cheeks; replace the markings with the exact same pale pink fur and watercolor texture as the surrounding face. The face has naturally pale pink fur but NO extra cheek tint, no cheek circles or strokes. Keep the original rabbit identity: long upright ears, cream five-petal flower with yellow center on VIEWER'S RIGHT temple, oval brown eyes, small brown nose and gentle mouth, exact full-body standing neutral pose, short limbs, little tail, outline, proportions and texture otherwise unchanged. Do not invent a new design or reference any other company's mascot. Preserve genuinely transparent alpha background and all body/accessory margins. Exactly one isolated whole character, no text, scenery, props, cast shadow or white outline.
```

## ことり

ファイル：`bird.png`

```text
Use case: identity-preserve, precise-object-edit. Reference1 is NEW AUTHORITATIVE ORIGINAL supplied by user: the small yellow BIRD on the LEFT shelf beside the red lantern. Reference2 is a previous isolated draft, reference3 is finish style only. Update the standalone bird to match the new original more faithfully, preserving same warm brown outlines and subtle watercolor sprite finish. This specific bird has a very COMPACT ROUND body, round little head flowing into belly, tiny triangular warm-orange beak pointing toward VIEWER'S RIGHT, one oval dark-brown eye with a tiny white highlight, small folded wing drawn as a short warm orange curved line, and a distinctive SMALL THREE-ROUNDED-LOBED FAN TAIL sticking out on VIEWER'S LEFT like in reference1 (not the long single pointed tail in reference2). Two tiny simple brown-orange feet. No red/pink cheeks, blush circles, cheek strokes or new markings; entirely natural yellow. Neutral standard standing pose in right-facing three-quarter/profile, all feet and tail visible, no props or clothing. Preserve this original bird's recognizable silhouette; do not borrow any other mascot design. Exactly ONE whole bird centered on a square GENUINELY TRANSPARENT alpha canvas, character about65percent canvaswidth and55percent height with generous clear margins. No scene, shelf, lanterns, other creatures, floor, cast shadow, white sticker border, text or extra views.
```

## とら

ファイル：`tora.png`

```text
Use case: identity-preserve, background-extraction. Asset type: canonical reusable 2D game character base sprite, one character per image. Reference1 is the original character identity artwork. Reference2 is an APPROVED standalone bear BASE: match its warm brown outline thickness, soft watercolor texture, compact chibi proportions, friendly face rendering, camera angle and clean sprite finish, but draw ONLY the requested species. Preserve the specific reference character, not a generic mascot. Full body, almost directly front-facing, relaxed neutral standing pose, both feet fully visible at the same baseline, short paws resting naturally beside the torso, calm small smile. Square composition, centered with about10percent clear margins. GENUINELY TRANSPARENT alpha background; no floor, cast shadow, white sticker border, scenery, furniture, text, labels, other characters, duplicate views or props. Paint texture only inside the character. Never crop ears, feet, tail or accessory. Draw ONLY the ORANGE TABBY CAT matching the cat in original reference1 and reference3 picnic: rounded large cream/apricot face, triangular soft orange ears with pale pink interiors, three short warm-orange forehead stripes and two or three orange cheek stripes on each side, large dark-brown oval eyes with white highlights, tiny warm-brown triangular nose and gentle w-like smiling muzzle, three simple whiskers each side, warm creamy light golden body with soft orange tabby markings. Standing on two short rounded hind legs, short rounded forepaws at sides, whole orange-striped tail curved gently upward toward VIEWER'S RIGHT and entirely visible. No backpack, clothing, hat, mug or accessories. Preserve the broad short chibi cat proportions, not realistic feline anatomy. Match reference2 bear outline weight, color softness and face rendering. Character occupies about78percent of image height with tail included in margins. Exactly one isolated tabby cat base.
```

## 白い細身の子（種別未確定）

ファイル：`cream-companion.png`

```text
Use case: identity-preserve, background-extraction. Create exactly ONE standalone full-body base sprite of the WHITE/CREAM SLIM ANIMAL seated at the FAR LEFT of the classroom illustration reference1, typing at the desk. It is the larger cream creature BELOW the tiny round hamster perched on its head. Reference2 red boxes help locate it; ignore all red boxes and all other characters. Its species is not settled (possibly weasel/stoat); do NOT redesign it into a zoologically generic animal. Match the ORIGINAL silhouette and identity: light ivory cream fur, two softly pointed triangular ears, head somewhat more tapered than the round bear heads, a subtly elongated small muzzle facing left, warm brown oval eye with white highlight, tiny brown nose and small gentle smiling mouth, slimmer elongated upper torso and short rounded forepaws, compact hind legs. Keep a plain cream tail gently curved beside the body, no new black tail tip or new fur markings. Reference3 is warm brown outline thickness / watercolor paint-finish only; do not give it bear ears, bear muzzle, yellow fur or a red hat. Full-body quiet seated/standing-rest pose turned THREE-QUARTER TOWARD VIEWER'S LEFT as in the original, paws relaxed in front with no held object, body and all feet/tail fully visible. No tiny hamster on head, chair, desk, laptop, paint tools or clothing. NO red/pink cheek blush, cheek circles, diagonal cheek lines or makeup. Preserve source facial simplicity and proportions, no borrowing other company's character design. Square centered composition with10percent safe margins, character occupies75percent canvasheight. GENUINELY TRANSPARENT alpha background with no ground/castshadow/white border, no text, labels, props, other characters or extra poses. Exactly one complete original cream slim companion, species deliberately unlabelled.
```

## 模様のある猫（後ろ姿）

ファイル：`cat-patches-back.png`

```text
Use case: identity-preserve, background-extraction. Create exactly ONE standalone full-body base sprite of the PATCHED WHITE CAT in the CENTER-LEFT foreground of original classroom reference1, seen FROM BEHIND, immediately left of the pink rabbit. The user explicitly identifies this as a separate patterned cat, NOT the orange striped character. Reference2 helps locate it, ignore red rectangles. Reference3 only sets warm brown handdrawn outline quality and subtle watercolor paint finish. The original shows a broad round white/cream cat head from back, softly triangular ears, a large dark chocolate-brown patch covering the VIEWER'S LEFT ear and upper left back-of-head, and a warm light orange/tan patch at the VIEWER'S RIGHT ear/head side. Preserve exactly this placement and source head silhouette. Complete its small plump white/cream body and short rounded back legs neutrally, with a simple cream cat tail gently visible toward one side; do not invent additional body stripes or elaborate new markings. IMPORTANT: source does not establish its face, so KEEP THE REAR VIEW for this canonical base; no invented frontal face. Rear-facing neutral standing pose, both arms resting near the body and both hind feet completely visible, head looking forward away from viewer as in original. No chair, desk, other animals, hamster, laptop, garments, bags or props. NO red/pink blush or cheeks in any visible part. Preserve original character identity, not a generic famous mascot. One centered complete cat back-view on square GENUINELY TRANSPARENT alpha background, about75percent canvasheight with clear margins, no floor/cast shadow/white sticker border, no text, labels, additional views or scene. Exactly one original patched cat base.
```

