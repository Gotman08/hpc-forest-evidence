param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$InputSha256
)
$ErrorActionPreference = 'Stop'
$readerPath = Join-Path $PSScriptRoot 'lecteureceive_q15.py'
$readerSha = (Get-FileHash -LiteralPath $readerPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($readerSha -ne '9ef06b3441e7a767d7549a39044273b34094a9042fb3d1e8588febcb2c54a634') { throw 'Reader source SHA changed; new review required.' }
& python -B $readerPath --input $InputFile --input-sha256 $InputSha256
exit $LASTEXITCODE
