# Dev Cockpit

A personal, reproducible developer environment for macOS, Linux and native Windows, with Catppuccin Mocha throughout.

## Install

Install the whole cockpit with one command. Each launcher installs by default (no flags needed): **core + cockpit + terminal**.

macOS / Linux:

```sh
curl --proto '=https' --tlsv1.2 -fsSL https://raw.githubusercontent.com/UtkarshBhardwaj007/dev-cockpit/main/bootstrap/setup.sh | sh
```

Windows PowerShell:

```powershell
& ([scriptblock]::Create((Invoke-RestMethod https://raw.githubusercontent.com/UtkarshBhardwaj007/dev-cockpit/main/bootstrap/setup.ps1)))
```

This installs:

- **core**: git, gh, ripgrep, fd, fzf, zoxide, lazygit, delta, yazi, starship, mise, bat, eza, jq, uv, direnv (zsh plugins on Unix)
- **cockpit**: herdr + OMP (coding agent + workspace orchestrator)
- **terminal**: Ghostty (macOS/Linux) or WezTerm (Windows) + JetBrainsMono Nerd Font

These commands execute code from this public repository. For inspection before executing, clone it and run the local entrypoint, or preview with `sh bootstrap/setup.sh --dry-run`. `main` moves; release pinning and signed distribution remain on the roadmap. [Security model](docs/security.md)

Requires **Python 3.9+**. The launcher provisions Python (plus Homebrew on macOS/Linux, or WinGet on Windows) automatically when missing. See [prerequisites](docs/customization.md#prerequisites).

## Optional add-ons

`history` (atuin) and `extras` (btop) are **not** installed by default — they remain opt-in profiles. From a checked-out repository on macOS/Linux:

```sh
sh bootstrap/setup.sh --install --profile history --profile extras
```

On Windows:

```powershell
& .\bootstrap\setup.ps1 -Install -Profile history,extras
```

## Install a selected profile

From a checked-out repository on macOS/Linux:

```sh
sh bootstrap/setup.sh --install --profile core --profile cockpit --profile terminal
sh bootstrap/setup.sh --apply-config
sh bootstrap/setup.sh --doctor --profile core --profile cockpit --profile terminal
```

On Windows:

```powershell
& .\bootstrap\setup.ps1 -Install -Profile core,cockpit,terminal
& .\bootstrap\setup.ps1 -ApplyConfig
& .\bootstrap\setup.ps1 -Doctor -Profile core,cockpit,terminal
```

An existing file is preserved unless this project previously created it and its content has not been edited. Config application does not modify shell profiles, Git identity, SSH settings or agent credentials. Explicit shell activation is documented in [customization](docs/customization.md).

| Profile | Contents | Default | Installer coverage |
|---|---|---|---|
| `core` | git, gh, ripgrep, fd, fzf, zoxide, lazygit, delta, yazi, starship, mise, bat, eza, jq, uv, direnv | yes | Homebrew on Unix; WinGet on Windows |
| `cockpit` | Herdr and OMP | yes | Release download on Unix and Windows (binaries to `~/.local/bin`) |
| `terminal` | Ghostty on Unix, WezTerm on Windows | yes | macOS cask / Windows WinGet; Linux installs via distro package or pinned .deb on Ubuntu/Debian/Arch/openSUSE, else prints guidance |
| `history` | Atuin | no (opt-in) | Homebrew / WinGet; no sync, import or shell capture automatically enabled |
| `extras` | btop | no (opt-in) | Homebrew on Unix; not available on Windows |

Profiles select packages, not config: `--apply-config` applies the common themed configuration set. Repeat `--profile` on Unix, or use `-Profile core,cockpit` on Windows. `--install` preflights selected missing manual adapters and stops before package changes if one is required. Package installation skips binaries already on PATH; version compatibility is not yet enforced.

## Next commands

Open Ghostty (or another terminal) and start a new session so the shell functions load, or source the activation snippet in the current shell. Then:

| Command | What it does |
|---|---|
| `dev` | Re-run install and config; idempotent and safe to repeat |
| `dev open .` | Open the current project in a Herdr cockpit workspace (OMP + Yazi + shell panes) |
| `dev-doctor` | Check installed binaries and configuration status |
| `dev-update` | Refresh managed config and install package updates |
| `dev-uninstall` | Remove unchanged project-owned config; packages stay installed |
| `dev-completions` | Refresh stale shell completions (`--force` to regenerate) |
| `dev memory <subcommand> .` | Manage local project memory, e.g. `dev memory show .` |
| `dev graph <subcommand> .` | Build or query the local code graph, e.g. `dev graph init .` |
| `herdr` | Start the Herdr multiplexer directly |
| `omp` | Start the OMP coding agent directly |
| `yazi` / `y` | File manager; `y` returns to the directory you quit in |
| `lg` | lazygit |
| `ll` / `lt` | eza long and tree listings |
| `dg` | git with delta paging |

Start with `dev-doctor` if a command is missing; it reports PATH and config status. See [shell activation](docs/customization.md#activate-the-shell) and [intelligence](docs/intelligence.md) for details.

## Theme

- Ghostty: bundled Catppuccin Mocha, comfortable padding and a subtle translucent background.
- WezTerm: bundled Catppuccin Mocha, compact tab bar, steady cursor.
- Herdr: built-in Catppuccin.
- OMP: built-in dark/light Catppuccin, with memory off initially.
- Starship: official Catppuccin Powerline preset.
- Yazi: official Catppuccin Mocha with mauve accents.

Install **JetBrainsMono Nerd Font** separately for the preset's full glyphs. Font installation and desktop visual acceptance are follow-up work. Vendored themes carry their licenses and exact upstream revisions in [licenses/sources.json](licenses/sources.json).

## Develop and remove configuration

```sh
python3 -m unittest discover -s tests -v
python3 bootstrap/cockpit.py --platform windows --dry-run
python3 bootstrap/cockpit.py --uninstall-config
```

Use `python` or `py -3` on Windows. Uninstall removes only unmodified files owned by this project. User-edited files, packages, shell profiles, agent data and credentials remain. Empty directories and the ownership ledger are retained.

See [validation](docs/validation.md) before interpreting CI as a claim of full desktop or hardware compatibility.
