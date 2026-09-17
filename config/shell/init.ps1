# Managed activation for native PowerShell 5.1 and 7. No startup downloads.
if (Get-Variable -Name DevCockpitInitialized -Scope Global -ErrorAction SilentlyContinue) { return }
$global:DevCockpitInitialized = $true
if (-not $env:DEV_COCKPIT_CONFIG_DIR) { $env:DEV_COCKPIT_CONFIG_DIR = $PSScriptRoot }
$dcEnvironment = Join-Path $env:DEV_COCKPIT_CONFIG_DIR 'environment.ps1'
if (Test-Path -LiteralPath $dcEnvironment) { . $dcEnvironment }
$dcUserHome = $env:DEV_COCKPIT_USER_HOME
if (-not $dcUserHome) { $dcUserHome = $env:USERPROFILE }
foreach ($dcBin in @((Join-Path $dcUserHome '.local/bin'), (Join-Path $dcUserHome '.bun/bin'), (Join-Path $dcUserHome '.local/share/dev-cockpit/graphify/bin'))) {
    if ((Test-Path -LiteralPath $dcBin -PathType Container) -and ($env:PATH -split [IO.Path]::PathSeparator) -notcontains $dcBin) {
        $env:PATH += [IO.Path]::PathSeparator + $dcBin
    }
}
function global:Invoke-DevCockpit {
    $runtime = Join-Path $env:DEV_COCKPIT_ROOT 'bootstrap/cockpit.py'
    if (-not (Test-Path -LiteralPath $runtime)) { throw 'Dev Cockpit runtime is missing. Rerun setup to repair it.' }
    & $env:DEV_COCKPIT_PYTHON $runtime @args
}
# `dev` runs the full setup by default; known subcommands pass through so the
# documented forms (`dev open .`, `dev memory show .`, `dev graph init .`) work.
if (-not (Get-Command dev -ErrorAction SilentlyContinue)) {
    function global:dev {
        $dcSubcommands = 'launch', 'doctor', 'update', 'uninstall', 'completions', 'mobile', 'memory', 'graph', 'open'
        if ($args.Count -gt 0 -and $dcSubcommands -contains $args[0]) { Invoke-DevCockpit @args }
        else { Invoke-DevCockpit launch @args }
    }
}
if (-not (Get-Command dev-doctor -ErrorAction SilentlyContinue)) { function global:dev-doctor { Invoke-DevCockpit doctor @args } }
if (-not (Get-Command dev-update -ErrorAction SilentlyContinue)) { function global:dev-update { Invoke-DevCockpit update @args } }
if (-not (Get-Command dev-uninstall -ErrorAction SilentlyContinue)) { function global:dev-uninstall { Invoke-DevCockpit uninstall @args } }
if (-not (Get-Command dev-memory -ErrorAction SilentlyContinue)) { function global:dev-memory { Invoke-DevCockpit memory @args } }
if (-not (Get-Command dev-graph -ErrorAction SilentlyContinue)) { function global:dev-graph { Invoke-DevCockpit graph @args } }
if (-not (Get-Command dev-completions -ErrorAction SilentlyContinue)) { function global:dev-completions { Invoke-DevCockpit completions @args } }
if ((Get-Command eza -ErrorAction SilentlyContinue) -and -not (Get-Command ll -ErrorAction SilentlyContinue)) {
    function global:ll { & eza --long --group-directories-first --git --icons=auto @args }
}
if ((Get-Command lazygit -ErrorAction SilentlyContinue) -and -not (Get-Command lg -ErrorAction SilentlyContinue)) {
    function global:lg { & lazygit @args }
}
if ((Get-Command delta -ErrorAction SilentlyContinue) -and -not (Get-Command dg -ErrorAction SilentlyContinue)) {
    function global:dg { & git -c ('include.path=' + (Join-Path $env:DEV_COCKPIT_CONFIG_DIR 'delta.gitconfig')) @args }
}
if ((Get-Command yazi -ErrorAction SilentlyContinue) -and -not (Get-Command y -ErrorAction SilentlyContinue)) {
    function global:y {
        $temporary = [IO.Path]::GetTempFileName()
        try {
            & yazi @args ('--cwd-file=' + $temporary)
            if ((Get-Item -LiteralPath $temporary).Length -gt 0) {
                $selected = [IO.File]::ReadAllText($temporary).TrimEnd("`r", "`n")
                if (Test-Path -LiteralPath $selected -PathType Container) { Set-Location -LiteralPath $selected }
            }
        } finally { Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue }
    }
}
# Native PowerShell picker, without a third-party PSFzf module.
if ((Get-Command fzf -ErrorAction SilentlyContinue) -and -not (Get-Command ff -ErrorAction SilentlyContinue)) {
    function global:ff {
        if (Get-Command fd -ErrorAction SilentlyContinue) { & fd --type f --hidden --exclude .git | & fzf @args }
        else { Get-ChildItem -File -Recurse | ForEach-Object { $_.FullName } | & fzf @args }
    }
}
if (-not $env:FZF_DEFAULT_OPTS) {
    $env:FZF_DEFAULT_OPTS = '--height=60% --layout=reverse --border --color=bg+:#313244,bg:#1e1e2e,fg:#cdd6f4,fg+:#cdd6f4,hl:#f38ba8,hl+:#f38ba8,pointer:#f5e0dc,marker:#b4befe,spinner:#f5e0dc,header:#f38ba8,info:#cba6f7,prompt:#cba6f7'
}
if ($env:DEV_COCKPIT_SKIP_PSREADLINE -ne '1') {
    try {
        Import-Module PSReadLine -ErrorAction Stop
        $dcOptionCommand = Get-Command Set-PSReadLineOption -ErrorAction Stop
        if ($dcOptionCommand.Parameters.ContainsKey('PredictionSource')) {
            Set-PSReadLineOption -PredictionSource History -ErrorAction Stop
        }
    } catch { Write-Verbose ('PSReadLine: ' + $_.Exception.Message) }
}
$dcCompletions = Join-Path $env:DEV_COCKPIT_CONFIG_DIR 'completions/powershell'
if (Test-Path -LiteralPath $dcCompletions) {
    foreach ($dcCompletion in (Get-ChildItem -LiteralPath $dcCompletions -Filter '*.ps1' -File)) {
        try { . $dcCompletion.FullName } catch { Write-Verbose ('Optional completion: ' + $_.Exception.Message) }
    }
}
# Evaluate at the dot-source scope so upstream definitions survive initialization.
if ((Get-Command zoxide -ErrorAction SilentlyContinue) -and $env:DEV_COCKPIT_SKIP_ZOXIDE -ne '1' -and -not (Get-Command __zoxide_z -ErrorAction SilentlyContinue)) {
    try { $dcHook = & zoxide init powershell; if ($LASTEXITCODE -eq 0) { Invoke-Expression ($dcHook | Out-String) } } catch { Write-Verbose $_ }
}
if ((Get-Command mise -ErrorAction SilentlyContinue) -and $env:DEV_COCKPIT_SKIP_MISE -ne '1') {
    try { $dcHook = & mise activate pwsh; if ($LASTEXITCODE -eq 0) { Invoke-Expression ($dcHook | Out-String) } } catch { Write-Verbose $_ }
}
if ((Get-Command atuin -ErrorAction SilentlyContinue) -and $env:DEV_COCKPIT_SKIP_ATUIN -ne '1') {
    try { $dcHook = & atuin init powershell --disable-up-arrow; if ($LASTEXITCODE -eq 0) { Invoke-Expression ($dcHook | Out-String) } } catch { Write-Verbose $_ }
}
if ((Get-Command starship -ErrorAction SilentlyContinue) -and $env:DEV_COCKPIT_SKIP_STARSHIP -ne '1' -and -not $env:STARSHIP_SESSION_KEY) {
    $dcExistingStarship = Join-Path $env:USERPROFILE '.config/starship.toml'
    if ($env:XDG_CONFIG_HOME) { $dcExistingStarship = Join-Path $env:XDG_CONFIG_HOME 'starship.toml' }
    if (-not $env:STARSHIP_CONFIG -and -not (Test-Path -LiteralPath $dcExistingStarship)) {
        $env:STARSHIP_CONFIG = Join-Path $env:DEV_COCKPIT_CONFIG_DIR 'starship.toml'
    }
    try { $dcHook = & starship init powershell; if ($LASTEXITCODE -eq 0) { Invoke-Expression ($dcHook | Out-String) } } catch { Write-Verbose $_ }
}
Remove-Variable dcUserHome, dcEnvironment, dcBin, dcOptionCommand, dcCompletions, dcCompletion, dcExistingStarship, dcHook -ErrorAction SilentlyContinue
