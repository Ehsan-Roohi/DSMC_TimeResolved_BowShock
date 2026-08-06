$ErrorActionPreference = "Stop"
$Repo = "Ehsan-Roohi/DSMC_TimeResolved_BowShock"
if (Get-Command gh -ErrorAction SilentlyContinue) {
  gh repo create $Repo --public --source . --remote origin --push
} else {
  Write-Host "GitHub CLI is not installed. Create an empty public repository named DSMC_TimeResolved_BowShock, then run:"
  Write-Host "git remote add origin https://github.com/$Repo.git"
  Write-Host "git push -u origin main"
}
