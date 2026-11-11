# 動画制作ツールの確認・更新

2026年11月11日、このMac（Apple Silicon）で上流の安定版と実際の実行環境を照合しました。リリース候補・開発版を最新安定版として採用していません。

| ツール | 確認前 | 制作環境の版 | 対応 |
|---|---|---|---|
| Python | 3.15.2 | 3.15.2 | 最新安定版のため維持 |
| Pillow | 13.0.0 | 13.0.0 | 最新安定版のため維持 |
| Node.js | 26.13.0 LTS | 26.13.0 LTS | 最新安定版のため維持 |
| npm | 12.2.2 | 12.2.2 | 最新安定版のため維持 |
| Git | Apple Git 2.54.0 | 2.56.1 | 上流の安定版をユーザー領域へ導入 |
| Git LFS | 3.8.1 | 3.8.1 | 最新安定版のため維持 |
| FFmpeg / ffprobe | 未導入 | 9.0.2 | 公式ソースからarm64用にビルドして導入 |
| pip（仮想環境） | 26.2.2 | 26.3 | 更新 |
| kokoro-js | 1.2.1 | 1.2.1 | 最新安定版のため維持 |
| @huggingface/transformers | 3.8.1 | 3.8.1 | Kokoroが対応する最新3系を維持（下記参照） |
| @huggingface/jinja | 0.5.11 | 0.5.12 | 現在の依存範囲内の安定パッチへ更新 |

## 音声処理ライブラリの互換性

Transformers.js全体の最新安定版は4.3.2です。一方、現行のkokoro-js 1.2.1が宣言する依存は `@huggingface/transformers: ^3.5.1` で、対応範囲内の最新は3.8.1です。現行ツールはモデルとトークナイザーをKokoroへ渡すため、直接依存だけを4系に変えると、Kokoro内部の3系Tensorと4系モデルの型が一致しません。実際の4系入力検証器でも `style` / `speed` の入力エラーを再現しました。

今回は3.8.1を維持し、未対応のメジャー更新を強制するoverrideや独自互換レイヤーは導入していません。ONNX Runtime・sharp・protobufjsも、親パッケージの対応範囲と固定版を守ります。Nodeで使う推論実行環境は `onnxruntime-node 1.21.0` です。ロック内の `onnxruntime-web` は親が固定した開発版を含みますが、このMacのCPU推論には使用しません。

## このMacでの使用

```sh
cd /Users/support/codex/youtube
source .venv/bin/activate
python --version
git --version
git lfs version
ffmpeg -version
ffprobe -version
node --version
npm --version
```

新しいGitとFFmpegは `/Users/support/.local/share/youtube-toolchain/` に保存し、`.venv/bin/` からリンクしています。共有Homebrewの所有権・アクセス権や、AppleのシステムGitを変更していません。別のPCではこれらの絶対パスをコピーせず、各環境で同じ版を用意してください。

JavaScript依存は更新後の `package-lock.json` で `npm ci` を実行しました。Python依存は `requirements.txt` のPillow 13.0.0です。新規音声生成・認識に使うモデルは、既存の固定revisionとSHA-256に従って `.model-cache/` へ取得します。過去の採用モデル・採用音声・完成動画の記録は変更しません。

```sh
python tools/portable_models.py --cache-root .model-cache --model all --check-only
```

過去の完成品を再出力する場合は、その作品のGit LFS実体を別途取得してください。ランタイムの動作確認は、過去作品を全編再検査した記録ではありません。

## 検査記録と出典

更新後に既存の関連テスト81件、1080p/30fpsのH.264＋AAC書き出しと全編デコード、PCM変換、素数モックアップの新規描画、Kokoroの音声生成、Whisperの数値・文の認識、CTC音素認識を確認しました。新規描画の代表PNGは元のモックアップとSHA-256が一致しました。

最初のASR動作確認では数列の台詞が数字を連結した `2357.` と認識され、文字列比較の警告が出ました。この結果も保持し、別の数値型入力と自然な文で認識経路を確認して2件とも一致しました。制作音声の採用検査や全編試聴の代わりにはしていません。結果の入口は [summary.json](../reproducibility/toolchain-audit-20261111/summary.json) です。

[今回の確認記録](../reproducibility/toolchain-audit-20261111/)に、更新前の版、上流URL、ソースと実行ファイルのハッシュ、互換性の検証、実行結果を保存します。

- [Python公式リリース](https://www.python.org/downloads/)
- [Node.js公式ダウンロード](https://nodejs.org/en/download)
- [Git公式インストール案内](https://git-scm.com/install/)
- [Git LFS公式リリース](https://github.com/git-lfs/git-lfs/releases)
- [FFmpeg公式ダウンロード](https://ffmpeg.org/download.html)
- [pipのPyPI配布](https://pypi.org/project/pip/26.3/)
- [PillowのPyPI配布](https://pypi.org/project/Pillow/13.0.0/)
- [Kokoroのnpm配布情報](https://registry.npmjs.org/kokoro-js/1.2.1)
- [Transformers.js 4.3.2公式リリース](https://github.com/huggingface/transformers.js/releases/tag/4.3.2)
