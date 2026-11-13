# ヤイロチョウの限定リメイク記録

利用する画像は、他の素材と同じ [current の登録](../../current/asset.json) から `expanded/think` を選びます。通常姿は維持します。

正式版全739枚の原寸点検で見つかった細部だけを対象に、新しい原画を作成し、原寸・明暗・同尺度の通常姿と前後姿勢で比較しました。この登録は全27姿勢のうち1姿勢だけを選び直し、良好な26姿勢の原画・登録、元のシート、通常姿と既存clipを保持します。

- [採用判断と新旧SHA](selection-v001.json)
- [登録](registration.json)・[尺度と足支点の根拠](registration-calibration-v001.json)
- [静止・離散姿勢の確認範囲](geometry-review-v001.json)
- [全姿勢一覧](pose-review.png)・[離散キーポーズGIF](key-pose-preview.gif)
- [固定原画による比較設定](comparison-review-v001.json)。「前バージョン」と「AIおすすめ」の印を付けています。判断はユーザーから委任されたAIのもので、ユーザーのクリックとして記録していません。
- [正確な生成指示](provenance/tool-arguments-v001.json)・[実入力の保存先とSHA](provenance/input-snapshots-v001.json)・[無改変原画の来歴](provenance/output-record-v001.json)

内蔵の `image_gen.imagegen` を使い、生成された1254×1254の透過PNGを無改変で保存しました。モデル識別子は非公開のため推測していません。原寸静止画と離散キーポーズの採用判断であり、アプリの補間・実時間再生・完成MP4の合格とは区別します。過去の画風指摘と当時のQAは元登録に保持しています。
