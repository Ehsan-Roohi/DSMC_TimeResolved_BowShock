$ErrorActionPreference = "Stop"

$PackageRoot = $PSScriptRoot
$ConfigPath = (Resolve-Path (Join-Path $PackageRoot "config\all_kn_campaign_config.json")).Path
$Config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$ResultsRoot = [System.IO.Path]::GetFullPath([string]$Config.paths.results_root)
$ResolvedConfig = Join-Path $ResultsRoot "qc\resolved_campaign_config.json"
$ScriptsDir = Join-Path $PackageRoot "scripts"

Write-Host "Package root:    $PackageRoot"
Write-Host "Results root:    $ResultsRoot"
Write-Host "Resolved config: $ResolvedConfig"

Set-Location $ScriptsDir

if (-not (Test-Path $ResolvedConfig)) {
    Write-Host "Resolved config does not exist. Running QC V2 first..."
    python run_all_kn_analysis.py --config $ConfigPath --stage qc
    if ($LASTEXITCODE -ne 0) {
        throw "QC failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path $ResolvedConfig)) {
    throw "Resolved campaign config was not created at: $ResolvedConfig"
}

Write-Host "Running ten-snapshot remap pilot..."
python run_remap_pilot.py --config $ResolvedConfig --count 10
if ($LASTEXITCODE -ne 0) {
    throw "Remap pilot failed with exit code $LASTEXITCODE"
}

$PilotSummary = Join-Path $ResultsRoot "remap_pilot\remap_pilot_summary.csv"
Write-Host ""
Write-Host "REMAP PILOT COMPLETE"
Write-Host "Summary: $PilotSummary"
