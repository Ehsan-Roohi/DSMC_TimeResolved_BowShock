param(
  [int]$Bootstrap = 500
)
$ErrorActionPreference = "Stop"

$MainRoot = Split-Path $PSScriptRoot -Parent
$Config0 = Join-Path $MainRoot "config\all_kn_campaign_config.json"
if (-not (Test-Path $Config0)) {
  throw "This folder must be inside JFM2_ALL_KN_UNIFIED_ANALYSIS. Missing: $Config0"
}
$Cfg0 = Get-Content -Raw $Config0 | ConvertFrom-Json
$ResultsRoot = [System.IO.Path]::GetFullPath([string]$Cfg0.paths.results_root)
$Resolved = Join-Path $ResultsRoot "qc\resolved_campaign_config.json"
$Out = Join-Path $ResultsRoot "DISPLACEMENT_TEMPLATE_VALIDATION"
$MainScripts = Join-Path $MainRoot "scripts"
$LocalScripts = Join-Path $PSScriptRoot "scripts"
$Script = Join-Path $LocalScripts "displacement_template_validation.py"

if (-not (Test-Path $Resolved)) { throw "Missing resolved config: $Resolved" }
$env:PYTHONPATH="$MainScripts;$LocalScripts;$env:PYTHONPATH"

Write-Host "Running synthetic self-test..."
python $Script --self-test
if ($LASTEXITCODE -ne 0) { throw "Self-test failed." }

Write-Host ""
Write-Host "Running the final full-field displacement-template validation."
Write-Host "Cases: Kn0p01, Kn0p025, Kn0p050"
Write-Host "Variables: D, MA, TTR, P"
Write-Host "Raw snapshots: common200 only"
Write-Host "Output: $Out"

python $Script `
  --config $Resolved `
  --out $Out `
  --cases Kn0p01 Kn0p025 Kn0p050 `
  --variables D MA TTR P `
  --count 200 `
  --bootstrap $Bootstrap `
  --block 8 `
  --grad-fraction 0.10 `
  --weight-power 1.0 `
  --reuse-cache

if ($LASTEXITCODE -ne 0) {
  throw "Displacement-template validation failed."
}

Write-Host ""
Write-Host "FINAL PHYSICAL VALIDATION COMPLETE"
Write-Host "Send the output folder or ZIP it with ZIP_RESULTS.ps1."
