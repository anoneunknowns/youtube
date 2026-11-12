# Powers of 2 制作版v002の入口

完成候補: [output/powers-of-two-counting-001-v001/video/v004-audio-reencoded/paspla-studio-powers-of-two-1-to-18446744073709551616-1080p.mp4](../../output/powers-of-two-counting-001-v001/video/v004-audio-reencoded/paspla-studio-powers-of-two-1-to-18446744073709551616-1080p.mp4)

SHA-256: `ff0375d857354285fa9aebbe08f3f95072fd7f8ce9ed97947e0b3c0ada602e61`。1920×1080、30fps、16,954frame、565.133333秒。
制作記録: [production-run-v002.json](production-run-v002.json)。台本: [production/scenario-v002.txt](production/scenario-v002.txt)。
レビュー: [production-review-v002.txt](production-review-v002.txt)。

数学・英語・台詞・発話時刻・画像・演技は保ち、短burstを是正した新しいAACを同じH.264へコピーする。
原音の選定75新規＋3既存は継続し、今回の新規TTS・新規原画は0。旧版の採否・媒体・原本は保存する。
旧READMEはv003当時の再現説明として保全し、現行音声の採用先として使わない。

今回の音声設定と実測根拠:
再検査で見つかった音声不具合と修正

旧v003のN029（536,870,912）、170.437354167秒に、採用PCMにはない短いAAC復号振動が存在した。48kHz sample8180993のPCM16値は旧AAC左−24551／右4115に対し、当時のmaster左右796。平均音量・全発話相関・音声認識だけでは短い異常を見逃すため、初回fresh音声PASSはaudio-pass-supersession.jsonで撤回した。旧媒体・旧QA・元音源は保全する。

同じ全編位相でdefault圧縮対照が異常を再現。PNS無効で主要burstは消失し、さらにIS無効でN033の局所残差が4971から1032PCM16へ改善した。MSはautoを維持し、-aac_coder twoloop -aac_is 0 -aac_pns 0、48kHz stereo／192kbps指定で圧縮する。全工具offや強制MSは通常残差が増えるため採らない。原因・採否はcodec-choice-comparison.jsonに記録した。

旧N029全発話窓の追加−3.5dBは符号化後ピークへの対処だった。新設定は元のaudio-build/master.wavを不変で参照し、他の数詞と同じ元音量へ戻す。新規TTS発話0、新規画像0。75新規採用原音＋既存採用3の選択、速度、全78語句、字幕、数学状態、発話時刻を維持する。

新候補の全編局所screenは最大左右差68PCM16、元masterへの最大残差1136PCM16。唯一のX030 triggerは183.132583／183.133583秒で、10ms誤差RMS−41.946／−41.332dBFS、誤差/参照−19.958／−19.756dB。出力/参照RMS差は約−0.12dB、左右同一、同cue残差peak923・最大左右差2。生警告を消さず、新規局所ASR/CTCと結び通常のcodec近似として個別判断する。全78発話・左右の新規認識／語頭／語尾と最終採否は新音声レビューへ束縛する。

rootの別経路復号でも旧burstの解消を確認した。AACのinput-side seekを用いた初回差分は位相がずれた計測として棄却し保存。全編decodeからサンプル番号で切り出したroot-n029-candidate-check-v002.jsonを有効証拠とする。

画像はv003と同じH264を再符号化せずcopyし、全packetのpayload／PTS／DTS／durationと全16,954復号フレームの一致で新MP4へ映像検査を継承する。今回の独立数学3731照合、不一致0と、新規全編映像・原寸字形・24動作・fade検査の証跡はrecheckフォルダに保全する。全65項、64倍増、最終値18,446,744,073,709,551,616は正しい。

実施範囲は全編の自動解析・新規音声推論とassistantによる原寸抽出画像／個別証拠の確認。人による9分25秒の全編連続視聴・試聴の記録とは区別する。最終のMP4・AAC・timeline・採否はfinal-verification.jsonのSHA束縛を参照する。


- 実測timeline: `output/powers-of-two-counting-001-v001/audio-build/codec-v003/timeline.json`
- 現行master: `output/powers-of-two-counting-001-v001/audio-build/master.wav`
- 採用AAC: `output/powers-of-two-counting-001-v001/audio-build/codec-v003/accepted-aac.m4a` / SHA `6e3cbac811194a930b9523eb0a8546f3932199e695db9770d126f244a5218e3b`
- 補正: `output/powers-of-two-counting-001-v001/audio-build/codec-v003/correction.json`
- 最終QA: `design/powers-of-two-counting-v1/recheck-20261112-v001/final-verification.json`
- 新AAC採否: `output/powers-of-two-counting-001-v001/recheck-20261112-v001/audio-correction-v001/candidate-review.json`
- copyと全映像同一性: `output/powers-of-two-counting-001-v001/video/v004-audio-reencoded/render-manifest-v004.json`
- 実際のremux実装: `output/powers-of-two-counting-001-v001/recheck-20261112-v001/video/remux-audio-v004-v002.py`

再現には保存v003を映像parentとし、新採用AACをstream-copyする。実コマンド・タグ・検証条件は上の実装とmanifestの記録を使用する。
旧v003構築手順で再現したAACを現行へ取り違えない。出力先は毎回新規にし、採用済み媒体を上書きしない。
reference-v002の元画像はv003由来のまま保全し、全picture同一性の証跡でv004へ継承する。

この文書生成時点では共有台帳・CURRENT・archiveを変更していない。後続のroot登録とcloseoutで現行採用を確定する。
