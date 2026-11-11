# キャラクター反応素材 v2：生成記録

作成日: 2026-11-03（日本時間）。組み込み `image_gen` を使用。原画を `view_image` で確認してから、原画を参照して各キャラ1枚の4列×3行透過PNGを生成した。全キャラに頬紅を追加しない。ハムスターに手足を足さない。猫の左右の模様を反転しない。小さいくまは帽子のくまより一回り小さく表示する。数値の身長比は従来の暫定値を保持し、ユーザーが数値まで承認したものとは扱わない。

原画・旧48ポーズは上書きせず、現行ゲームへの採用は別作業。以下はツールへ送信したプロンプトそのもの。初回のくま・とら・白い細身の子・模様のある猫は余白、セル境界へのはみ出し、不要な光を修正し、修正版を採用した。計8回の初回生成と4回の修正生成を行った。未採用画像は `design/character-reactions-v2/revisions/` に記録する。

## bear-beret

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character is the pale lemon-yellow bear with round ears, giant round head, stocky short body, two simple mitten arms, two stubby feet, tiny roundtail, dark brown oval eyes with slim original white outer eye areas, distinctive outlined muzzle/nose and small pink tongue. Preserve red beret with tiny top nub in EVERY pose. No outfit. Never orange fur. Signature in cell12: beret has slipped forward over ONE eye, bear tilts head and nudges it back with one paw, playful rather than distressed. Cell4 one paw by chin; cell5 one paw lifted; cell11 paw-to-paw clap. Keep original facial/muzzle structure and no extra cheek markings.
```

## bear-small

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: the original small warm-ivory bear, with same huge round head, round ears, short stocky torso, small mitten arms and stubby legs; original oval brown eyes with white outer eye areas, distinctive outlined muzzle and tiny pink tongue. Pale ivory not yellow; no hat/accessory. The little round tail must stay SCREEN LEFT in frontal poses. Do not make it taller/longer than the reference. Cell4 both paws near muzzle, leaning curiously; cell5 one raised paw; cell11 broad shy but excited two-paw wave. Cell12 SIGNATURE: stands on tiptoes and wobbles trying to look bigger, elbows out for balance, funny earnest little face. Do not add motionline objects, props or effects.
```

## hamster

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: the original LIMBLESS warm cream hamster from the reference. ONE continuous plump short rounded softly upright/rounded-rectangle blob, height only about1.09 times width, round little ears on top, two plain dark-brown oval dot eyes with NO white areas or glints, distinctive small INVERTED W / M-shaped dark-brown mouth. Do NOT lengthen lower body or add a separate head/torso, arms, hands, legs, feet, fingers, whiskers, nose, teeth or tail. All12poses must keep this SAME simple compact limbless anatomy. Emotion comes only from oval/dot or simple curved closed eyes, subtle M-mouth changes, ear tilts, and whole-body posture. Cell2 slight down squish ONLY5%; cell3 small upward spring; cell4 whole blob leans15degrees inquisitively; cell5 ears upright and alert; cell6 subtle anticipation; cell7 whole blob lifted with happy closed eyes, NO appended limbs; cell8 small squash. Cell9 gentlytilted body, one ear lowered, puzzled ovaleyes, originalMmouth. Cell10 straightens with encouraging closedeyes; cell11 happy diagonal body sway, ears up. Cell12 SIGNATURE: one roundear flops slightly inward while the compact whole blob tilts the other way, endearing uneven pose. Keep it a compact hamster, not a long ricecake/cylinder or conventional animal with arms.
```

## rabbit-flower

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: original pale pink rabbit, very large round head with TWO long rounded upright ears, white five-petal flower with yellowcenter at the base of SCREEN RIGHT ear (anatomical LEFT), and small round tail SCREEN RIGHT. Two simple mittenarms, shortbody/stubbylegs, original large oval brown eyes with whiteareas, tinybrownnose and simple w-like smile. Keep original pink body uniformly pink, no cheekredness or new facial spots. Preserve long ears and the SAME flower screenright in ALL frontal poses, no mirroring. Ears may lean/bend softly but never become short or duplicated. Full long ears fit with transparent padding in everycell. Cell4 paw bychin, one ear tilted inquisitively; cell5 paw up and both ears alert; cell7 joyful broadtwo-armjump with ears trailing slightly,not a differentrabbit; cell9 tiny puzzledheadtilt, one ear leans; cell10 reaches invitingpaw outward; cell11 happy little two-paw dance. Cell12 SIGNATURE: one very long ear has softly flopped forward over the topofhead and rabbit looks up at it with amusedeyes, flower remainsat SAME screenright anatomicalearbase, not on theother side. No objects other than originalflower.
```

## bird

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: original simple PALE YELLOW little bird. Use the supplied slightly thicker-contour bird as soleidentityreference. Keep mostly the SAME LEFT-FACING threequarter/side silhouette. A smooth roundhead continuously becomes plumpbody, tinyorangebeak, plain small brown DOTeye with ABSOLUTELY NO white/highlight/glint/eyelash, SINGLE softly up-pointing tail, TWO tinyorangefeet. Wing is originally ONE simple curved brownstroke; when raised it can be a single simple smooth flipperoutline, never detailed featherdrawing. No bellypatches, decorative orange feather lines, spottedwings, crest, clothes, fannedtail or exoticbird features. Preserve gentle brownlineweight.
Use only a minimaldot or simpleclosedeyecurve for expressions. Cell1 oneclosedeyecurve; cell2 slightlylowersbody; cell3 quicksmallhop wingsslightlyout; cell4 inquisitiveheadtilt; cell5 alertupwardlook wingraises; cell6 crouch; cell7 joyfulsmallflight TWO simplewings raised just enough, twofeet tucknaturally, keepone originaltail; cell8 land wingstuck; cell9 headtilt andsingleplaineye; cell10 invitinglittlewingwave; cell11 happyflutter with simpleclosedeye. Cell12 SIGNATURE: twists ONLY its head around toward its own single raisedtail, curious, thebody still facesleft; donot mirrorwholebird. No fruit/flowers/props. Keep it intentionally SIMPLE and unornamented like theoriginal.
```

## tora

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: the original small friendly tiger TORA, PALE cream/apricot fur, huge round head, TWO softly triangular ears with pale pink inner areas, original large brown ovaleyes with white outerarea, small trianglebrownnose with u/w smile. Short roundbody, simple mittenarms, stubbylegs, three warm orange vertical stripes on forehead plus original paired orange face/bodystripes and THREE simple whiskerlines each side. Long gentlycurve stripedtail naturally on SCREEN RIGHT in frontal poses. Keep same originalstripe positions/colors and right-side tail consistently; do not add bold blacktigerstripes or realisticfangs. No newprops or clothes.
Cell4 pawbychin and tailcurled softly; cell5 brightfaceonepawup; cell7 jubilant two-armjump, same headsize; cell9 ears slightlyinclined puzzledface; cell10 friendlypawout; cell11 bouncy happy two-pawwave. Cell12 SIGNATURE: tiger glances sideways at the tip of its OWN right-side tail which has curled upward beside its cheek, both paws halfready to catch it, playful curiousface. Tailmustremainconnected on same screenright body side, no detachedduplicate.
```

## cream-companion

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: original slim ivory/cream companion shown in reference, species intentionally UNDETERMINED: do not redesign as a ferret, stoat, fox, rabbit or familiarbrandmascot. Preserve two soft triangular upright ears with pink innerarea, broadsofthead, brown ovaleyes with white outerareas, roundedbrownnose, simple smilingmouth, uniquely longSLIM neck/torso, small delicatelyoutlined forepaws and hindfeet, plaincreamtail naturally screenLEFT. There are tiny simple originaltoe marks, preserve without humanfingers. NO yellowfur, dark ear tips, coloredmarkings, hairtuft, newaccessoryoroutfit. This one is graceful and springy rather thanstocky like thebears. Keepslimbody/headratio constant as body bends, do not turninto short bear.
Cell4 headtilt with two forepaws near chest; cell5 alert oneforepawup; cell7 joyful longlimbed butsameanatomy airborne hop, tailcurvedleft; cell9 slight sideways lean inquisitiveface; cell10 gentleopenforepaw invitation; cell11 happy springydance. Cell12 SIGNATURE: slimbody makes a playful sideways C-curve as if a softspring, head gentlyleansoppositehips and own tail curlsaroundscreenLEFT side, impish happyface. No motionlineeffectsorprops, noextraanimal.
```

## cat-patches

```text
Use case: identity-preserve / illustration-story.
Asset type: production 2D game character reaction sprite atlas. The input is the ONLY original character identity reference; derive poses of that same individual, not a redesign or an imitation of any other mascot.
Output ONE high-resolution transparent PNG sprite sheet, ideally2048x1536, exactly FOUR equal columns by THREE equal rows, twelve equal square cells, in reading order. No drawn grid, no labels, numbers, words, border or watermark.
Every cell has exactly ONE complete full-body drawing of the SAME character. Keep the same drawing scale and head size between cells; changes in body posture do not mean changes in anatomical size. Fit each pose entirely INSIDE its own cell with at least8% transparent padding, allow headroom for hops. Use an invisible shared center x=50% and resting baseline y=88% within each cell; airborne poses lift from this baseline and must not be stretched or resized to fill the cell. No overlapping neighboring cells. Do not add any cast shadow, brown halo, glow, fog, colored background, simulated checkerboard or floor. Genuine transparent alpha outside the drawn outline is essential.
Match the reference's pale watercolor paper grain INSIDE the body, original warm dark-brown softly hand-drawn contour, face anatomy, proportions, body color, ear shapes and markings. Keep designs simple and legible at small game sizes. No red/pink cheeks, cheek strokes, blush or added face decorations in ANY pose. No extra appendages, duplicate limbs, human fingers, clothing, accessories or objects except the character's already-owned accessory explicitly specified. Emotional changes should be real eye/mouth/ear/body pose changes with readable silhouettes, not twelve near-identical neutrals.
The twelve cells in row-major order MUST be:
1 BLINK, peaceful short closed-eye smile, resting stance.
2 TAP DOWN, anticipation: slight squat/compress, attentive.
3 TAP POP, little startled delighted pop, visibly different from cell2.
4 THINK, gentle inquisitive head/body lean, eyes following puzzle.
5 AHA, sudden understanding, bright attentive face, own appendage lifted if anatomically present.
6 SUCCESS READY, deeper joyful crouch preparing a jump.
7 SUCCESS AIR, big joyous airborne pose with wide/open appendages where natural, feet/body lifted well above restbaseline.
8 SUCCESS LAND, soft landing, eyes happily closed, small compression.
9 OOPS, momentary puzzled surprise and slight lean, never fear, tears, shame or anger.
10 RETRY, regained confidence, warm encouraging gesture/face.
11 CHEER, an energetic distinct celebratory gesture/body pose.
12 SIGNATURE GAG, the specific personality gag described below, self-contained and amusing.
No speech or symbolic punctuation bubbles. Artwork only. Keep original design rather than adding details.
Character: original warmwhite PATCHED CAT, huge round head, softlytriangularears, large brown ovaleyes withwhiteouterareas, small triangularnose, simplew smile, threewhiskerlines eachside, roundbody/mittenarms/stubbylegs and ONE long WHITEtail on screenRIGHT. CRITICAL IDENTITY: FRONTSCREEN LEFT ear+upperheadpatch is LIGHTORANGE. FRONTSCREEN RIGHT ear+upperheadpatch is DARKCHOCOLATEBROWN. Whitecentralblaze,lowerfaceandbody. Keep this SPECIFIC asymmetry in ALL12cells, evenwhenleans; NEVERTOTALMIRROR. Originalnoadditionalfurpatches, stripedtailornewspots. Matchsource watercolor texture. Nooutfits.
Cell4 pawnearcheek, thoughtfulheadlean with originalorangeleft/brownright maintained; cell5 onepawup; cell7 joyfultwoarmjump, samepatterns; cell9 oneear slightlytilts, gentlesurprise; cell10 invitingpawreach; cell11 playfulonefootdance. Cell12 SIGNATURE: cat peeks sideways toward its own white tail tip brought upbeside cheek on the SCREENRIGHT, chinleaned and pleasedcuriousface, forepaws heldplayfullynearbody. Tail staysattachedonright and earsremainorangeleft/brownright. No balls, flowers, hearts, sparkles or otherobjects; only thecat.
```

## bear-beret：修正

```text
Use case: precise-object-edit. The supplied image is the edit target, a4-column3-row transparent sprite atlas of one original yellow bear with redberet. Preserve EXACTLY its twelve poses, their row-majororder, each face, beret, color, watercolorpapergraintreatment and anatomy. Correct ONLY spacing: make EACH of the12drawings approximately15percent SMALLER within its OWNcell, uniformly inx/y, while keeping a sharedrestbaseline near88percent ofcellheight. Keep eachheadthesame anatomicalsize relativetoothers; no stretching or pose redesign. In particular the airbornebear at row2column3 must have at least25px transparent space ABOVEitsberet at1448x1086totalresolution (orproportional8percentcellpadding at anotherresolution). The restbaseline staysput; jumpingpose remappingmaybringit slightlylower while retaining an obviousairbornegap. Make sure at least8percent clear margin exists around EVERY completeposedrawingandallaccessories within EACH squarecell. Keep EXACT4columns×3rows twelveequal SQUAREcells,1448×1086preferred, plaintransparentbackground with zerooutsidealpha except antialiasedge. No gridlines, frameborders, words, letters,numbers, watermark,props,glow,brownhalo,shadowsorground. Do not change characteridentityorexpressions. No blush orcheektint. OutputONLY correctedtransparentPNGatlas.
```

## tora：修正

```text
Use case: precise-object-edit. The supplied image is the ONLYedit target, a4column3row transparent atlas of12poses ofouroriginalpaletiger. Retain the SAME twelvecharacters/poses/faceexpressions/positions/order, samepaleapricotcolor, orangeforeheadandfacestripes, whiskers, curvedtailonSCREENRIGHT, anatomy, watercolorpaperfillandbrownoutline. RemoveALL unwanted NON-CHARACTER imagery: remove the two light-gray/whiteglowingcircularorbs (onejustleftoffirstrowfirstcharacterandoneaboverightoflastrowlastcharacter), and removeALL thegray/yellow/red coloredhaze, halo, glow, lightblobs, fog, floatingpixels and backgroundmottling aroundcharacters. Thoseareas must become GENUINELYTRANSPARENTalpha0, notcoveredwithwhite/black/anothercolor. Preserve ONLY actualtigers withcrispnaturalantialiasededges. Noadded effects or shadows anywhere. Eachcell must contain ONLY one tiger, nootherobjectsorlight. Keep4columns×3rows ofequal SQUAREcells and all12posesinexactreadingorder. Noformatlayoutchanges. Alsoensure no tail/whisker/eartouches a cellborder; ifnecessaryslightly reduceeachentiretigertoabout90percent withinitsowncell, withatleast8percenttransparentpadding, preservingaspectratioandcomparablescaleacrosscells. No words, numbers, labels, checkerboard orgrid. Absolutelynoblush, cheekredness, newprops, newlimbsorredesign. OutputONLYcleantransparentPNGatlas.
```

## cream-companion：余白の修正

```text
Use case: precise-object-edit. The suppliedimage is the edit target: a FOURcolumn by THREErow transparent atlas containing12poses ofONEoriginal ivoryslimcompanionwithtriangular earsandplain tail onscreenLEFT. Correctonlylayout/padding, preserveall12poses, exactidentity, faces, slimneckbody, originaltoeandpawlines, creamcolorsandwatercolorgrain. Atrow2column3, itsjumpingheadcurrentlycrossesintothecellabove. THISMUSTBECORRECTED. ReduceALL12completeposedrawings uniformlyby20percent insidetheirowncells, sameanatomicalscaleandpreservedaspectratio. Positioneach fulldrawingtohaveatleast35pxcleartransparentspaceaboveandbelowandleft/rightinsideitsOWNcellat1448x1086canvas. Originalcellgridis4x3each362pxsquare. AIRBORNErow2column3 mustbeCOMPLETELYcontainedinits362x362cellwith35pxmargins; neverletits ears/bodyleakintorow1column3. Keeporiginalposeandfeetliftintentvisiblewithoutscalingbodytofitdifferentlyfromotherposes. Keep4x3equalSQUAREcellgridandrowmajororder, noresizingofgrid. Restbaselinecanmoveupslightlytomakepadding. RemoveANYhaloglowfogisolatedpixelsorcastshadowoutsidedrawings; genuinealpha0outsideartwithedgeantialiasonly. No labels,numbers,lines,checkerboard,background,watermark,newobjectsorcharacters. No cheekblushorredness, noaddedstripesorclothes. ThisisONLYpaddingcorrectionNOTredesign. OutputONLYcorrectedtransparentPNG.
```

## cat-patches：余白の修正

```text
Use case: precise-object-edit. The suppliedimage is theedit target: a4column3row transparentatlas containing12poses ofONEoriginalpatchedcat. CorrectONLYspacing/padding. Preserve EXACTLY all12poses/expressions, anatomy, watercolorpapergrain/colors. CRITICALpreservefrontSCREENLEFT lightorangeear/headpatch andSCREENRIGHT darkbrownear/headpatch withwhiteface/body, andtheonewhitetailonscreenRIGHT. NEVERmirrororaddcoloredpatches.
MakeALL12drawings uniformlyabout18percentsmallerintheirOWNcells withthesameanatomicalscaleandpreservedaspectratio. Atleast30pxcleartransparentspacebetweenALLactualdrawnparts(includingears/whiskers/tail) andEACHowncellborderat1448x1086canvas. Especiallyrow2column3jumpingcat needs30pxclearspaceABOVEtheears, nowtootight. Restbaselinearound87percentofcell, airbornejumpstillliftedbutallpartsinsidesamecell. EXACTFOURcolumns×THREErows withtwelveequalSQUAREcells, readingorderunchanged. Noartcrossingcellborders. Keeporiginalhead/bodyratio; noindependentx/yscale/stretch, noautomaticallyenlargingjumpdrawing.
Outsideeachcatmustbegenuinealpha0exceptnaturalantialiasingedge. No halo/shadow/glow/fog/ground/disconnectedspecks/sparkles. No frames, labels, numbers,letters,checkerboardorbackground. Nocheekblush/redness,newlimbs,clothes,propsorre-design. OutputONLY correctedtransparentPNG.
```


