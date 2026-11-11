$ErrorActionPreference = 'Stop'
$taskCache = 'D:/dev/caches/huggingface/onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX'
$revision = 'c69750f5043e5e1f8a71ab95dd3b98338c280c92'
$files = @('config.json', 'preprocessor_config.json', 'special_tokens_map.json', 'tokenizer_config.json', 'vocab.json', 'README.md', 'onnx/model_quantized.onnx')
foreach ($file in $files) {
    $target = Join-Path $taskCache $file
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if (-not (Test-Path -LiteralPath $target)) {
        $part = "$target.download"
        & curl.exe --fail --location --silent --show-error --output $part "https://huggingface.co/onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX/resolve/$revision/${file}?download=true"
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $file" }
        Move-Item -LiteralPath $part -Destination $target
    }
}
$model = Join-Path $taskCache 'onnx/model_quantized.onnx'
if ((Get-Item -LiteralPath $model).Length -ne 317712852 -or (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant() -ne '3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120') {
    throw 'Phoneme model integrity mismatch'
}
$receipts = foreach ($file in $files) { $target = Join-Path $taskCache $file; [pscustomobject]@{file=$file;bytes=(Get-Item -LiteralPath $target).Length;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()} }
$receiptPath = 'D:/temp/youtube-audio-qa/phoneme-model-files.json'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $receiptPath) | Out-Null
[pscustomobject]@{model='onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX';revision=$revision;license='Apache-2.0';files=@($receipts)} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8NoBOM
Write-Output 'Phoneme model downloaded and SHA-256 verified.'
