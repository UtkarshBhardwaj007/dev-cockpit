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

The snippets initialize Starship and zoxide when present, and expose `dev` (install/config) plus `dev open .` (open a project in Herdr). They do not automatically start Herdr, install shell plugins, initialize mise environment hooks, enable Atuin history capture or register MCP servers. Use upstream mise activation once your desired project runtime policy is chosen.

On bash 4 or newer the snippet also loads Homebrew's `bash-completion@2` automatically, so the `~/.bash_profile` line Homebrew prints after installing it is not required. Apple's `/bin/bash` 3.2 cannot load bash-completion v2, but dev-cockpit still registers its own completions and Git's completion there. The login profile (`.bash_profile`, `.bash_login` or `.profile`, whichever exists first) and `.bashrc` both receive the managed block, so login and non-login interactive bash are covered.

## Herdr and OMP

Install both, start OMP once and authenticate with the provider of your choice. Then review and run the first-party integration installer:

```sh
herdr integration install omp
```

This writes an OMP extension; the upstream documentation explains its location and removal. Do not set Pi and OMP to the same agent directory. The integration lets Herdr identify OMP and resume a saved conversation after a restart. [Integration reference](https://herdr.dev/docs/integrations/#omp)

Run `dev open .` from a project to create (or reuse) a Herdr workspace with OMP, Yazi and a shell pane, or start `herdr` directly and open a workspace yourself. Yazi does not automatically follow another pane's cwd. Keep `omp` directly available when diagnosing the multiplexer.

Inside Yazi, `Enter` opens text and code files in `$EDITOR` (set to `nvim`, `vim`, `hx` or `nano` when the variable is unset), `b` opens the interactive opener chooser (`bat`, editor, reveal), `q` quits and changes the shell directory, and `Q` quits without changing it. The `fe` and `fv` shell helpers use `fzf` with a `bat` preview to edit or page a file from anywhere.

## Trackpad pinch-to-zoom for Herdr panes (macOS)

Herdr zooms the focused pane from its right-click menu or `prefix+z`. A trackpad pinch is an AppKit gesture event that reaches the terminal emulator, never the pty, so Herdr and its plugins cannot observe it. Dev Cockpit therefore ships an opt-in `gestures` profile that installs [Hammerspoon](https://www.hammerspoon.org/) and a small bridge: pinch out zooms the focused pane, pinch in unzooms it, and both work in Ghostty and WezTerm.

```sh
sh bootstrap/setup.sh --install --apply-config --profile gestures
```

This installs the Hammerspoon cask, launches it, writes `~/.hammerspoon/init.lua`, and adds `ctrl+alt+shift+f1`/`ctrl+alt+shift+f2` bindings to Herdr's `config.toml`. The bridge watches gesture events and forwards that synthetic chord to the frontmost terminal; Herdr maps it to `pane zoom --on` / `--off`, so the command runs inside the focused pane and targets that pane's own session (including named sessions such as `dev-cockpit`). The chord is used instead of bare F13/F14 because Ghostty cannot encode F13/F14 — its legacy key table stops at F12 and it does not enable the kitty keyboard protocol — while `ctrl+alt+shift+F1/F2` is encoded as `ESC [ 1;8P`/`ESC [ 1;8Q` and decoded by Herdr. Ghostty and WezTerm claim no F-key bindings by default.

Two manual steps remain, because they cannot be automated safely:

1. Grant Hammerspoon **Accessibility** permission (System Settings → Privacy & Security → Accessibility). Without it the event tap observes nothing and pinches keep their normal terminal behavior. **Quit and reopen Hammerspoon afterwards** — macOS caches the trust decision for a process that was already running when the grant was made, so "Reload Config" alone does not pick it up. The bridge re-checks every few seconds and on macOS's Accessibility-state change notification, so it also starts on its own if the grant lands while it is running. The bridge shows a startup alert that says whether the tap is really running, so a missing grant is visible instead of silent.
2. If you already had a `~/.hammerspoon/init.lua`, the installer preserves it (files you created are never touched), so the bridge is not loaded automatically. Add `dofile("/path/to/dev-cockpit/config/hammerspoon/init.lua")` to your existing config, or copy the bridge contents into it.

If Hammerspoon was already running when the installer wrote `~/.hammerspoon/init.lua`, it will not pick up the bridge until you choose **Reload Config** from its menu. Press `ctrl+alt+cmd+z` in any app to print the bridge status: whether the tap is running, whether Accessibility is granted, and which app is frontmost. That hotkey is registered through macOS's Carbon hotkey API, so it still answers when Accessibility is missing — use it as the first diagnostic, and do not read "the hotkey works" as "Accessibility is granted".

Herdr reads `config.toml` at startup and does not watch it, so a session that was already running when the installer rewrote the file keeps the old bindings. Reload it with `herdr server reload-config` (add `--session dev-cockpit` before the subcommand when you use a named session), or restart Herdr. Without this the pinch reaches Herdr but no binding matches it.

`gestures` is macOS-only; `--profile gestures` is a no-op on Linux and Windows. Because this profile also selects config, add `--profile gestures` to your usual `dev` or `dev-update` profile list to keep the bridge refreshed; without it an already-installed bridge is left untouched. `--uninstall-config` removes the bridge along with the rest of the managed config; the Hammerspoon cask itself is left installed like every other package.

## Theme and existing configuration

The installer stores its Starship config under the platform config directory's `dev-cockpit` folder, selected by `STARSHIP_CONFIG`. Ghostty, WezTerm, Herdr and Yazi use their ordinary config locations.

`dev`, `dev-update` and the one-line launchers repair every file this project created, even if it was edited afterwards (Herdr rewrites its own `config.toml`, for example). The previous content is backed up under `dev-cockpit/backups` before each repair. Files you created yourself are never touched, so a personal `~/.config/starship.toml` or `~/Library/Application Support/com.mitchellh.ghostty/config.ghostty` stays yours. Direct `python3 bootstrap/cockpit.py --apply-config` remains the conservative mode that preserves edited files; add `--force-config` to repair.

The initial palette is Catppuccin Mocha. In Starship, change the palette to `catppuccin_latte` for light mode. Ghostty/WezTerm/Herdr have matching built-in themes; Yazi needs the corresponding licensed theme asset. Editing an installed file hands control back to you: future applies preserve it. Change the repository source to update an unedited managed file.

## Optional tooling

- Atuin: `--profile history` installs the binary only. Review storage and shell capture before adding its shell initialization; sync and account creation stay explicit.
- Hammerspoon: `--profile gestures` installs the cask and the Dev Cockpit pinch-to-zoom bridge on macOS only. It runs host-level Lua and needs the Accessibility permission; see the pinch-to-zoom section above.
- direnv: initially omitted because mise also handles project environments; never automatically approve `.envrc`.
- Mem0: not installed; compare OMP built-in memory first. Local summary processing can still call a hosted model.
- Graphify: not installed; choose a single repo and benchmark local code extraction before adding its MCP server or hooks.
- Codex / Claude Code: reuse existing authenticated installations. No model keys or tokens belong in this repository.

## Troubleshooting

`--doctor` reports PATH presence only. A missing GUI executable may be installed outside PATH; use its platform launcher and verify separately. Reopen terminals after WinGet installs. Homebrew/WinGet failures return nonzero and preserve earlier completed package installs; rerun after fixing the reported error. Packages are not rolled back automatically.

The ownership ledger is `dev-cockpit/ownership.json` under the same platform config directory. Do not edit it to claim ownership of personal files. Invalid ledger JSON or a symlink/junction in a target path stops config mutation. This prototype assumes one installer at a time; concurrent writes are not supported.
