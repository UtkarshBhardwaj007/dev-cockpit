# Customization and operation

## Prerequisites

The first bootstrap requires Python 3.9+. The one-liner auto-provisions Python (plus Homebrew on macOS/Linux, or WinGet on Windows) when it is missing, so manual installation is normally unnecessary. As an alternative, you can install Python yourself first: use `brew install python` with an existing Homebrew installation, your Linux distribution's Python package, or an official Python Windows installation. Reopen the terminal and verify `python3 --version` or `py -3 --version`. Windows Store execution aliases are not sufficient unless they launch an installed interpreter.

For package installation, install [Homebrew](https://docs.brew.sh/Installation) on macOS or supported Linux, or use [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/) on Windows. Homebrew's Linux build prerequisites and supported glibc/architectures still apply. Run this bootstrap as your own user, not through `sudo`.

## Activate the shell

Apply config first. Then source the generated snippet in an interactive session to try it:

```sh
. "${XDG_CONFIG_HOME:-$HOME/.config}/dev-cockpit/init.sh"
```

For persistence, add that line once to `.zshrc` or `.bashrc`. On Windows:

```powershell
. (Join-Path $env:APPDATA 'dev-cockpit/init.ps1')
```

Add it once to the PowerShell profile you use. The installer preserves your profile because deciding which existing prompt/hooks to replace requires inspection. Avoid initializing two prompt systems at once. Shell support in this milestone is bash, zsh and PowerShell; fish/Nushell need their own snippets.

The snippets initialize Starship and zoxide when present, and expose `dev` to launch Herdr. They do not automatically start Herdr, install shell plugins, initialize mise environment hooks, enable Atuin history capture or register MCP servers. Use upstream mise activation once your desired project runtime policy is chosen.

## Herdr and OMP

Install both, start OMP once and authenticate with the provider of your choice. Then review and run the first-party integration installer:

```sh
herdr integration install omp
```

This writes an OMP extension; the upstream documentation explains its location and removal. Do not set Pi and OMP to the same agent directory. The integration lets Herdr identify OMP and resume a saved conversation after a restart. [Integration reference](https://herdr.dev/docs/integrations/#omp)

Start `dev` (or `herdr`), open a project workspace, and launch `omp`, `yazi` and a shell in separate panes. Automated layout provisioning is the next integration milestone. Yazi does not automatically follow another pane's cwd. Keep `omp` directly available when diagnosing the multiplexer.

## Theme and existing configuration

The installer stores its Starship config under the platform config directory's `dev-cockpit` folder, selected by `STARSHIP_CONFIG`. Ghostty, WezTerm, Herdr and Yazi use their ordinary config locations; existing files are skipped. Merge the relevant settings manually if you already have custom configs.

The initial palette is Catppuccin Mocha. In Starship, change the palette to `catppuccin_latte` for light mode. Ghostty/WezTerm/Herdr have matching built-in themes; Yazi needs the corresponding licensed theme asset. Editing an installed file hands control back to you: future applies preserve it. Change the repository source to update an unedited managed file.

## Optional tooling

- Atuin: `--profile history` installs the binary only. Review storage and shell capture before adding its shell initialization; sync and account creation stay explicit.
- direnv: initially omitted because mise also handles project environments; never automatically approve `.envrc`.
- Mem0: not installed; compare OMP built-in memory first. Local summary processing can still call a hosted model.
- Graphify: not installed; choose a single repo and benchmark local code extraction before adding its MCP server or hooks.
- Codex / Claude Code: reuse existing authenticated installations. No model keys or tokens belong in this repository.

## Troubleshooting

`--doctor` reports PATH presence only. A missing GUI executable may be installed outside PATH; use its platform launcher and verify separately. Reopen terminals after WinGet installs. Homebrew/WinGet failures return nonzero and preserve earlier completed package installs; rerun after fixing the reported error. Packages are not rolled back automatically.

The ownership ledger is `dev-cockpit/ownership.json` under the same platform config directory. Do not edit it to claim ownership of personal files. Invalid ledger JSON or a symlink/junction in a target path stops config mutation. This prototype assumes one installer at a time; concurrent writes are not supported.
