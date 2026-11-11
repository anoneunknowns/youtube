param(
    [string]$CacheRoot = 'D:\dev\caches\huggingface',
    [string]$TempRoot = 'D:\temp'
)
$ErrorActionPreference = 'Stop'
$registeredPath = @([Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User')) -join ';'
$env:Path = ((@($registeredPath -split ';') + @($env:Path -split ';')) | Where-Object { $_ } | Select-Object -Unique) -join ';'
$projectRoot = Split-Path -Parent $PSScriptRoot
$receiptPath = Join-Path $projectRoot 'assets/library/audio/speech/kokoro-af-heart/v002/model-files.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
$resolvedCache = [IO.Path]::GetFullPath($CacheRoot)
$modelDirectory = [IO.Path]::GetFullPath((Join-Path $resolvedCache $receipt.model_id))
New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
foreach ($file in $receipt.files) {
    $target = [IO.Path]::GetFullPath((Join-Path $modelDirectory $file.relative_path))
    if (-not $target.StartsWith($modelDirectory + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Model file resolves outside the designated cache directory'
    }
    if (Test-Path -LiteralPath $target) {
        $existing = Get-Item -LiteralPath $target
        $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($existing.Length -ne $file.bytes -or $hash -ne $file.sha256) {
            throw "Existing model cache failed verification; preserve and inspect it: $target"
        }
        Write-Output ("Verified cached model file: " + $file.relative_path)
        continue
    }
    $temporary = Join-Path $TempRoot ('youtube-model-' + [guid]::NewGuid().ToString('N') + '.download')
    $url = 'https://huggingface.co/' + $receipt.model_id + '/resolve/' + $receipt.revision + '/' + $file.relative_path + '?download=true'
    & curl.exe --location --fail --retry 2 --output $temporary $url
    if ($LASTEXITCODE -ne 0) { throw "Download failed; partial file remains at $temporary" }
    $download = Get-Item -LiteralPath $temporary
    $hash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($download.Length -ne $file.bytes -or $hash -ne $file.sha256) {
        throw "Downloaded model file failed verification; inspect $temporary"
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Move-Item -LiteralPath $temporary -Destination $target
    Write-Output ("Installed verified model file: " + $file.relative_path)
}
