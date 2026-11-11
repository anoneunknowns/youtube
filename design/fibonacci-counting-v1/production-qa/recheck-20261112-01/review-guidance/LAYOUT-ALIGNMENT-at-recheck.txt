# 枠内の上下左右中央揃えの受入仕様

枠内でコンポーネントを上下左右中央揃えにする意図がある場合、**描画後の実測で水平・垂直の両方が中央であることを確認する**。座標に中央値を渡したことや、片方の軸だけの合格を完了条件にしない。

## 対象と基準領域

- 設計時に各枠とコンポーネントへIDを付け、`horizontal: center`、`vertical: center` の意図を記録する。見出し、数値、説明文、カード、図形、複数要素のまとまりを含む。
- 枠線を除いた内側とpaddingから、配置先の有効領域 `content_box = [left, top, right, bottom]` を定義する。座標は出力画像のpx、右端・下端は含まない。
- 通常は対称paddingを使う。非対称paddingや光学的な補正を意図する場合は、その領域・補正理由を設計に明記する。検査後に基準領域をずらして合格にしない。
- 足支点への接地、行のベースライン、左揃え等を意図した部品へ、無条件に中央揃えを適用しない。複数行やラベル＋数値を一つのコンポーネントとした場合はグループ全体を測る。内部の行揃えやベースラインは別に確認する。

## 測定と合格条件

実際に描画された前景の可視範囲 `visible_box` と `content_box` を同一の座標系で測る。文字はフォントの行高・advance・描画原点ではなく、表示された字形の範囲を使う。画像は透明な余白込みのキャンバス寸法を可視範囲にしない。背景、親の枠線、影、対象外の装飾を測定へ混ぜない。

```text
target_x = (content_left + content_right) / 2
target_y = (content_top  + content_bottom) / 2
actual_x = (visible_left + visible_right) / 2
actual_y = (visible_top  + visible_bottom) / 2
dx = actual_x - target_x
dy = actual_y - target_y
```

次の全条件を満たした場合だけ合格とする。

1. 対象の可視範囲が検出でき、矩形と座標が有限・非空である。
2. `abs(dx) <= tolerance_px` と `abs(dy) <= tolerance_px` がそれぞれ成立する。符号付き差の合計・平均で相殺しない。
3. コンポーネント全体が有効領域内に収まり、文字や画像が切れていない。中心一致だけでは、はみ出しを合格にしない。
4. 測定用の前景レイヤー／マスクには対象全体と周囲の余白があり、測定領域の端に対象が接していない。既に切れたROIだけで中心を測らない。

原寸の描画レイヤーでは、整数pxへの丸めを考慮して両軸それぞれ0.5px以内を既定とする。完成MP4のデコード後は量子化・前景抽出差を考慮して原寸1px以内を既定とし、使用した閾値・抽出方法を記録する。許容差を拡大して位置ずれを隠さない。

## 検査を行う場面と記録

モックアップ、代表フレーム、完成映像で確認する。最短・最長の文言、最小・最大桁数、桁上がり、表示モード、複数行、フォントサイズ違い、表示サイズ変更を含める。アニメーションやフェードは入口・途中・出口を確認する。全状態を調べられる固定レイアウトは全状態で確認する。

検査記録には枠／コンポーネントID、場面・値・時刻、解像度、`content_box`、実測の`visible_box`、両中心、`dx`、`dy`、許容差、はみ出し・切れ、軸別と総合の合否、原寸確認画像を残す。測定不能・対象未検出を合格にしない。数値判定に加えて原寸で上下・左右の余白を確認する。

## 共通検査と回帰テスト

[`tools/component_alignment.py`](../tools/component_alignment.py) を共通の両軸検査として使える。これは測定専用で、位置の自動修正や原画の変更を行わない。

```python
from tools.component_alignment import raster_centering_report

# component_layer: 対象だけを描いたRGBA、または前景を抽出したL/1マスク。
# 枠・背景を含めず、対象の周囲に測定用の余白を残す。
report = raster_centering_report(
    component_layer, content_box=(20, 10, 120, 90),
    name="number-card/label", tolerance_px=0.5,
)
assert report["passed"], report
```

完成映像のRGBフレームでは、対象の前景を独立に抽出してから測る。ROIを使う場合は `origin_xy` で出力画像上の座標へ戻す。描画関数が返した予定座標だけを再比較して、実描画の検査を代用しない。

[`tests/test_component_alignment.py`](../tests/test_component_alignment.py) は、片軸だけ一致、逆方向のずれの相殺、中心一致でも枠外、非対称padding、半pxの丸め、ROI原点、複数行、透明余白、空の対象、測定端の切れを回帰検査する。

```powershell
python -m unittest discover -s tests -p test_component_alignment.py
```

既存作品の過去の検査記録は、その時点の検査範囲として保持する。この共通テストの合格だけで、既存全動画の配置を再検査したとは記録しない。新作・レイアウト変更時に対象シーンを上記条件で検査する。
