# Dev Cockpit

A personal, reproducible developer environment for macOS, Linux and native Windows, with Catppuccin Mocha throughout.

**Status: first working bootstrap milestone.** The reviewed architecture is Ghostty + Herdr on macOS/Linux and WezTerm + Herdr on Windows, with OMP and Yazi. The complete fresh-machine setup and workspace layout are still being built. [Decisions](docs/decisions.md) · [Compatibility review](docs/feasibility.md) · [Validation and roadmap](docs/validation.md)

## Try the bootstrap

The default is a **read-only preview**. It downloads this repository into a temporary directory, prints missing packages and proposed config files, then removes the temporary copy. It does not install tools or change dotfiles.

Requires **Python 3.9+**. This prerequisite is not automatically provisioned yet. Package installation additionally requires Homebrew on macOS/Linux, or WinGet on Windows. See [prerequisites](docs/customization.md#prerequisites).

macOS / Linux:

```sh
curl --proto '=https' --tlsv1.2 -fsSL https://raw.githubusercontent.com/UtkarshBhardwaj007/dev-cockpit/main/bootstrap/setup.sh | sh
```

Windows PowerShell:

```powershell
& ([scriptblock]::Create((Invoke-RestMethod https://raw.githubusercontent.com/UtkarshBhardwaj007/dev-cockpit/main/bootstrap/setup.ps1)))
```

These commands execute code from this public repository. For inspection before execution, clone it and run the local entrypoint. `main` moves; release pinning and signed distribution remain on the roadmap. [Security model](docs/security.md)

## Install a selected profile

From a checked-out repository on macOS/Linux:

```sh
sh bootstrap/setup.sh --install --profile core
sh bootstrap/setup.sh --apply-config
sh bootstrap/setup.sh --doctor --profile core
```

On Windows:

```powershell
& .\bootstrap\setup.ps1 -Install -Profile core
& .\bootstrap\setup.ps1 -ApplyConfig
& .\bootstrap\setup.ps1 -Doctor -Profile core
```

An existing file is preserved unless this project previously created it and its content has not been edited. Config application does not modify shell profiles, Git identity, SSH settings or agent credentials. Explicit shell activation is documented in [customization](docs/customization.md).

| Profile | Contents | Current installer coverage |
|---|---|---|
| `core` (default) | git, gh, ripgrep, fd, fzf, zoxide, lazygit, delta, Yazi, Starship, mise | Homebrew on Unix; WinGet on Windows |
| `cockpit` | Herdr and OMP | Homebrew on Unix; Windows currently prints official manual routes |
| `terminal` | Ghostty on Unix, WezTerm on Windows | macOS cask / Windows WinGet; Linux currently prints distro guidance |
| `history` | Atuin | Homebrew / WinGet; no sync, import or shell capture automatically enabled |

Profiles select packages, not config: `--apply-config` applies the common themed configuration set. Repeat `--profile` on Unix, or use `-Profile core,cockpit` on Windows. `--install` preflights selected missing manual adapters and stops before package changes if one is required. Package installation skips binaries already on PATH; version compatibility is not yet enforced.

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
