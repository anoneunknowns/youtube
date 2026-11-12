# トゥエ・モース動画 v003 の再出力

今回の依頼は前回修正後の完成済み v002 の細部再チェック。数列と音声を継承し、導入I003の小さい位置番号と大きい値を明示し、矢印先端の突起と接合部を整えた。採用結果は `production-run-v003.json` と `detail-recheck-20261112-v002/repair-v003/final-verification.json` を正本とする。v001/v002 の媒体・当時の記録・旧 renderer と今回の不採用draftは保全している。

採用入力は v001 の `audio-build/v002/timeline.json`、`accepted-audio.m4a`、同一キャラクター登録・背景・フォント。音声を新規生成・再符号化しない。元音声の再生成は同一性の代用にならない。新しい完成MP4についても全 AAC パケットと時刻・初期化を照合する。

リポジトリルートで、まだ存在しない専用出力先を指定する。

```sh
.venv/bin/python tools/render_thue_morse_video_v003_final.py \
  --timeline output/thue-morse-counting-001-v001/audio-build/v002/timeline.json \
  --encoded-aac output/thue-morse-counting-001-v001/audio-build/v002/accepted-audio.m4a \
  --out-dir output/thue-morse-counting-001-v003/reproduction-new
```

完成後は、生成された MP4 と同じ実測 timeline を `tools/export_thue_morse_delivery.py` に渡し、別の納品先へ字幕・チャプター・概要を書き出す。採用済みの出力先へ上書きしない。

```sh
.venv/bin/python tools/export_thue_morse_delivery.py \
  --timeline output/thue-morse-counting-001-v001/audio-build/v002/timeline.json \
  --video output/thue-morse-counting-001-v003/reproduction-new/paspla-studio-thue-morse-sequence-256-terms-1080p.mp4 \
  --out-dir output/thue-morse-counting-001-v003/reproduction-new-delivery
```

原寸字形の検査は旧 verifier の独立 oracle に今回の新説明 ID を加えた `detail-recheck-20261112-v002/repair-v003/final-pixels/verify_repaired_video.py` を用いる。単なる正常 decode と、説明動作・原寸の演技・画質の観察は別々に行う。全数式、置換動作、未読セルと読み終わりの進捗、音声、字幕の記録と検査範囲は最終 QA に束ねる。

この改訂で新しい画像原本は生成していない。既存の採用原本、共通縮尺、足支点と原画来歴は変更していない。新作時の制作素材数と、今回の改訂での生成数は区別する。
