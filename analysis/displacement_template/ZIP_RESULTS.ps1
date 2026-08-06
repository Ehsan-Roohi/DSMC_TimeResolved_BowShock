$ErrorActionPreference = "Stop"
$MainRoot = Split-Path $PSScriptRoot -Parent
$Config0 = Join-Path $MainRoot "config\all_kn_campaign_config.json"
$Cfg0 = Get-Content -Raw $Config0 | ConvertFrom-Json
$ResultsRoot = [System.IO.Path]::GetFullPath([string]$Cfg0.paths.results_root)
$Source = Join-Path $ResultsRoot "DISPLACEMENT_TEMPLATE_VALIDATION"
$ZipPath = Join-Path $ResultsRoot "JFM2_displacement_template_validation_to_send.zip"
if (-not (Test-Path $Source)) { throw "Missing output: $Source" }
Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$Source\*" -DestinationPath $ZipPath -Force
Write-Host "Created: $ZipPath"
