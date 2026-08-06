param(
  [int]$PowerReplicates = 100
)
$ErrorActionPreference = "Stop"

$PackageRoot=$PSScriptRoot
$MainPackage=Split-Path $PackageRoot -Parent

# This package should be copied into the root of JFM2_ALL_KN_UNIFIED_ANALYSIS.
$ConfigPath=(Resolve-Path (Join-Path $MainPackage "config\all_kn_campaign_config.json")).Path
$Config=Get-Content -Raw $ConfigPath | ConvertFrom-Json
$ResultsRoot=[System.IO.Path]::GetFullPath([string]$Config.paths.results_root)

$ReferenceDir=Join-Path $ResultsRoot "temporal_common200\Kn0p01"
$TargetRoot=Join-Path $ResultsRoot "TRANSITION_FULL_ANALYSIS\temporal_full"
$OutRoot=Join-Path $ResultsRoot "FINAL_STATISTICAL_GATE"
$Scripts=Join-Path $PackageRoot "scripts"
$MainScripts=Join-Path $MainPackage "scripts"

if (-not (Test-Path $ReferenceDir)) { throw "Missing reference: $ReferenceDir" }
if (-not (Test-Path $TargetRoot)) { throw "Missing target root: $TargetRoot" }

$env:PYTHONPATH="$MainScripts;$Scripts;$env:PYTHONPATH"

python (Join-Path $Scripts "sliding_window_robustness.py") `
  --reference-dir $ReferenceDir `
  --target-root $TargetRoot `
  --out (Join-Path $OutRoot "sliding_windows")

if ($LASTEXITCODE -ne 0) { throw "Sliding-window analysis failed." }

python (Join-Path $Scripts "final_power_exclusion.py") `
  --reference-dir $ReferenceDir `
  --target-root $TargetRoot `
  --out (Join-Path $OutRoot "power_exclusion") `
  --replicates $PowerReplicates

if ($LASTEXITCODE -ne 0) { throw "Power/exclusion analysis failed." }

Write-Host ""
Write-Host "FINAL STATISTICAL GATE COMPLETE"
Write-Host "Output: $OutRoot"
