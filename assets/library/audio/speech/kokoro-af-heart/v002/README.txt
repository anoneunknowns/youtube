Paspla Studio：採用音声ライブラリ v002

英語1〜300と固有セリフ11本を保持する。Kokoro-82M v1.0、af_heart、fp32、en-US、生成速度0.98、24kHz mono PCM16 WAV。生成後の再生速度変更は行っていない。

measurements.jsonが本文・実測尺・相対パス・各WAVのSHA-256の正本。speech-acceptance.jsonが採用ゲートの記録。voice-profile.jsonにこれらの固定hashと利用条件を記録した。clips/のWAVを次の動画でも再利用する。

6、36、80、81、88、181、188、274、288を修正した。抽出した音声の生成文脈と切出範囲はprovenance.jsonとprovenance/に保持する。rejected-source-hashes.jsonに一致する旧音声は使用しない。

全311本を単独の語認識と音素認識で確認した。無声音末尾56本は、語末の摩擦・破裂の後に母音様の有声成分が再出現しないか検査した。文脈付きの認識だけで発音の警告を解消しない。判断の理由と短語CTCの限界はqa/pronunciation-decision-notes.jsonに記載した。

自動解析には限界がある。人による全編試聴を行ったという記録ではなく、すべての発音が完全であることを保証するものでもない。新しい本文や異なる声・速度の音声は別に生成し、同じ検査と採用ゲートを通す。

tools/generate_speech.mjsは設定が一致するとこの採用版を優先して再利用する。mix時は--speech-acceptanceを必ず指定する。本文、WAV、マニフェスト、検査根拠のhashが変わった場合は再検査する。

原モデルはApache-2.0。model-card.md、model-files.json、licenses/に出典・モデル整合性・依存ライブラリの原利用条件を保持した。人物の音声をアップロードして複製したものではない。外部素材の権利や新たな公開ライセンスを付与する文書ではない。

過去の生成作業パスは実行時の記録であり依存先ではない。明示音素takeの元WAVは採用clipと同一bytesで、provenance-path-map.jsonが現行の保管先を示す。文脈から抽出した3本の生成元はprovenance/に保管済み。
