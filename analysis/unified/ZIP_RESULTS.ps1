$cfg = Get-Content "$PSScriptRoot\config\all_kn_campaign_config.json" | ConvertFrom-Json
$src = $cfg.paths.results_root
$zip = "$src`_to_send.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$src\*" -DestinationPath $zip -Force
Write-Host "Created: $zip"
