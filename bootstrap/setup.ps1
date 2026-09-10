# Public launcher; runs a read-only preview by default. Compatible with PS 5.1+.
param(
    [switch]$Install,
    [switch]$ApplyConfig,
    [switch]$UninstallConfig,
    [switch]$Doctor,
    [switch]$DryRun,
    [Alias('Profile')][string[]]$Profiles = @('core'),
    [string]$HomeDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$python = $null
$pythonPrefix = @()
foreach ($candidate in @('python3', 'python', 'py')) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) {
        $prefix = @()
        if ($candidate -eq 'py') { $prefix = @('-3') }
        & $found.Source @prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $found.Source; $pythonPrefix = $prefix; break }
    }
}
if (-not $python) { throw 'Python 3.9+ is required in this milestone. Install Python, reopen PowerShell and rerun.' }
$cliArgs = @()
foreach ($item in $Profiles) { $cliArgs += @('--profile', $item) }
if ($Install) { $cliArgs += '--install' }
if ($ApplyConfig) { $cliArgs += '--apply-config' }
if ($UninstallConfig) { $cliArgs += '--uninstall-config' }
if ($Doctor) { $cliArgs += '--doctor' }
if ($DryRun) { $cliArgs += '--dry-run' }
if ($HomeDirectory) { $cliArgs += @('--home', $HomeDirectory) }
$scratch = $null
try {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'cockpit.py'))) {
        $entrypoint = Join-Path $PSScriptRoot 'cockpit.py'
    } else {
        $ref = if ($env:DEV_COCKPIT_REF) { $env:DEV_COCKPIT_REF } else { 'main' }
        if ($ref -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Invalid DEV_COCKPIT_REF; use a tag or commit SHA.' }
        $scratch = Join-Path ([IO.Path]::GetTempPath()) ('dev-cockpit-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $scratch | Out-Null
        $archive = Join-Path $scratch 'repo.zip'
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/UtkarshBhardwaj007/dev-cockpit/zip/$ref" -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $scratch 'repo')
        $roots = @(Get-ChildItem -Directory (Join-Path $scratch 'repo'))
        if ($roots.Count -ne 1) { throw 'Unexpected repository archive layout.' }
        $entrypoint = Join-Path $roots[0].FullName 'bootstrap/cockpit.py'
    }
    & $python @pythonPrefix $entrypoint @cliArgs
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap failed with exit code $LASTEXITCODE" }
} finally {
    if ($scratch -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
