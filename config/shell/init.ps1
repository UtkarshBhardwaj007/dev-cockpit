if (Get-Variable -Name DevCockpitInitialized -Scope Global -ErrorAction SilentlyContinue) { return }
$global:DevCockpitInitialized = $true
$env:STARSHIP_CONFIG = Join-Path $env:APPDATA 'dev-cockpit/starship.toml'
if (Get-Command zoxide -ErrorAction SilentlyContinue) { Invoke-Expression (& zoxide init powershell | Out-String) }
if (Get-Command starship -ErrorAction SilentlyContinue) { Invoke-Expression (& starship init powershell | Out-String) }
function global:dev {
    if (Get-Command herdr -ErrorAction SilentlyContinue) { & herdr @args }
    else { Write-Error 'Herdr is missing. See the cockpit profile and docs/customization.md.' }
}
