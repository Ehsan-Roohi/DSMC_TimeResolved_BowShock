param(
  [int]$Count = 10
)
$ErrorActionPreference = "Stop"

$PackageRoot = $PSScriptRoot
$ConfigPath = (Resolve-Path (Join-Path $PackageRoot "config\all_kn_campaign_config.json")).Path
$Config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$ResultsRoot = [System.IO.Path]::GetFullPath([string]$Config.paths.results_root)
$ResolvedConfig = Join-Path $ResultsRoot "qc\resolved_campaign_config.json"
$ScriptsDir = Join-Path $PackageRoot "scripts"

if (-not (Test-Path $ResolvedConfig)) {
    throw "Missing resolved config. Run RUN_QC_FIRST.ps1 first. Expected: $ResolvedConfig"
}

Set-Location $ScriptsDir
python run_remap_pilot.py --config $ResolvedConfig --count $Count
if ($LASTEXITCODE -ne 0) {
    throw "Remap pilot failed with exit code $LASTEXITCODE"
}
