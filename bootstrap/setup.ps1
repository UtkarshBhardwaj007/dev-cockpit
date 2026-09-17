# Public native Windows launcher, PowerShell 5.1+. No flags installs the default cockpit (core + cockpit + terminal).
param(
    [switch]$Install,
    [switch]$ApplyConfig,
    [switch]$ActivateShell,
    [switch]$UninstallConfig,
    [switch]$Doctor,
    [switch]$DryRun,
    [Alias('Profile')][string[]]$Profiles,
    [string]$HomeDirectory,
    [string[]]$CliArguments = @()
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$hasAction = $Install -or $ApplyConfig -or $ActivateShell -or $UninstallConfig -or $Doctor -or $DryRun
if (-not $hasAction -and $CliArguments.Count -eq 0) { $Install = $true; $ApplyConfig = $true }
$mutate = ($Install -or $ApplyConfig -or $ActivateShell) -and -not ($DryRun -or $Doctor -or $UninstallConfig)
# The process PATH environment variable is 'Path' on Windows but 'PATH' on
# Unix, where $env: access is case-sensitive. Resolve it case-insensitively so
# this launcher works on every supported platform.
function Get-CockpitProcessPath {
    foreach ($name in @('Path', 'PATH')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ($null -ne $value) { return $value }
    }
    return ''
}
function Set-CockpitProcessPath {
    param([string]$Value)
    $name = if ($null -ne [Environment]::GetEnvironmentVariable('Path', 'Process')) { 'Path' } else { 'PATH' }
    [Environment]::SetEnvironmentVariable($name, $Value, 'Process')
}
function Update-CockpitPath {
    $additional = @((Join-Path $env:USERPROFILE '.local\bin'), (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'), (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'))
    foreach ($scope in @('Machine', 'User')) {
        $pathValue = [Environment]::GetEnvironmentVariable('Path', $scope)
        if ($pathValue) { $additional += $pathValue.Split(';') }
    }
    $existing = @()
    $current = Get-CockpitProcessPath
    if ($current) { $existing = $current -split ';' }
    $combined = ($additional + $existing | Where-Object { $_ } | Select-Object -Unique) -join ';'
    Set-CockpitProcessPath -Value $combined
}
function Find-CockpitPython {
    foreach ($candidate in @('python3', 'python', 'py')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) {
            # Skip Microsoft Store execution aliases; probing them can open Store.
            if ($found.Source -like '*\Microsoft\WindowsApps\python*.exe') { continue }
            $prefix = @()
            if ($candidate -eq 'py') { $prefix = @('-3') }
            & $found.Source @prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Executable = $found.Source; Prefix = $prefix } }
        }
    }
    foreach ($directory in @((Join-Path $env:LOCALAPPDATA 'Programs\Python'), (Join-Path $env:ProgramFiles 'Python312'))) {
        if (Test-Path -LiteralPath $directory) {
            foreach ($exe in @(Get-ChildItem -LiteralPath $directory -Filter python.exe -Recurse -ErrorAction SilentlyContinue)) {
                & $exe.FullName -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Executable = $exe.FullName; Prefix = @() } }
            }
        }
    }
    return $null
}
Update-CockpitPath
$python = Find-CockpitPython
if ($mutate -and -not (Get-Command winget -ErrorAction SilentlyContinue)) {
    # Official Microsoft bootstrap; avoid touching gallery trust settings.
    if (-not (Get-Module -ListAvailable Microsoft.WinGet.Client)) {
        if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
            Install-PackageProvider -Name NuGet -Scope CurrentUser -Force | Out-Null
        }
        Install-Module -Name Microsoft.WinGet.Client -Repository PSGallery -Scope CurrentUser -Force | Out-Null
    }
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager
    Update-CockpitPath
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet bootstrap failed; install Microsoft App Installer and rerun.' }
}
if (-not $python) {
    if (-not $mutate) { Write-Host 'PLAN: Python 3.9+ and WinGet would be provisioned during installation.'; return }
    & winget install --exact --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed with exit code $LASTEXITCODE" }
    Update-CockpitPath
    $python = Find-CockpitPython
    if (-not $python) { throw 'Python installer finished but no Python 3.9+ executable was found.' }
}
$cliArgs = @()
foreach ($item in $Profiles) { $cliArgs += @('--profile', $item) }
if ($Install) { $cliArgs += '--install' }
if ($ApplyConfig) { $cliArgs += '--apply-config' }
if ($ActivateShell) { $cliArgs += '--activate-shell' }
if ($UninstallConfig) { $cliArgs += '--uninstall-config' }
if ($Doctor) { $cliArgs += '--doctor' }
if ($DryRun) { $cliArgs += '--dry-run' }
if ($HomeDirectory) { $cliArgs += @('--home', $HomeDirectory) }
# Repair project-created config by default so one command lands every update.
# Files the user created themselves are still never touched.
if ($mutate) { $cliArgs += '--force-config' }
$cliArgs += $CliArguments
$scratch = $null
try {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'cockpit.py'))) {
        $entrypoint = Join-Path $PSScriptRoot 'cockpit.py'
    } else {
        $ref = if ($env:DEV_COCKPIT_REF) { $env:DEV_COCKPIT_REF } else { 'main' }
        if ($ref -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Invalid DEV_COCKPIT_REF; use a tag or commit SHA.' }
        $scratch = Join-Path ([IO.Path]::GetTempPath()) ('dev-cockpit-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $scratch | Out-Null
        $cache = if ($mutate) {
            if ($env:DEV_COCKPIT_CACHE) { $env:DEV_COCKPIT_CACHE } else { Join-Path $env:USERPROFILE '.cache\dev-cockpit' }
        } else { Join-Path $scratch 'cache' }
        $revision = if ($ref -match '^[0-9a-f]{40}$') { $ref } else {
            (Invoke-RestMethod -Uri "https://api.github.com/repos/UtkarshBhardwaj007/dev-cockpit/commits/$ref").sha
        }
        if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Invalid repository revision response.' }
        $archiveDirectory = Join-Path $cache 'archives'
        New-Item -ItemType Directory -Path $archiveDirectory -Force | Out-Null
        $archive = Join-Path $archiveDirectory ($revision + '.zip')
        $expected = $env:DEV_COCKPIT_SHA256
        if (-not $expected -and (Test-Path -LiteralPath ($archive + '.sha256'))) { $expected = (Get-Content -LiteralPath ($archive + '.sha256') -Raw).Trim() }
        if (-not (Test-Path -LiteralPath $archive) -or -not $expected -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) {
            $temporary = $archive + '.' + [guid]::NewGuid().ToString('N') + '.part'
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/UtkarshBhardwaj007/dev-cockpit/zip/$revision" -OutFile $temporary
                $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($env:DEV_COCKPIT_SHA256 -and $actual -ne $env:DEV_COCKPIT_SHA256) { throw 'Repository archive checksum mismatch.' }
                Move-Item -LiteralPath $temporary -Destination $archive -Force
                [IO.File]::WriteAllText(($archive + '.sha256'), $actual)
            } finally {
                if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
            }
        }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $scratch 'repo')
        $roots = @(Get-ChildItem -Directory (Join-Path $scratch 'repo'))
        if ($roots.Count -ne 1) { throw 'Unexpected repository archive layout.' }
        $entrypoint = Join-Path $roots[0].FullName 'bootstrap/cockpit.py'
        # One-line/piped installs run from a temporary scratch removed on exit;
        # persist a copy of the runtime so `dev` keeps working after this installer exits.
        $env:DEV_COCKPIT_DEPLOY_RUNTIME = '1'
    }
    $pythonExecutable = $python.Executable
    $pythonPrefix = $python.Prefix
    & $pythonExecutable @pythonPrefix $entrypoint @cliArgs
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap failed with exit code $LASTEXITCODE" }
} finally {
    if ($scratch -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
