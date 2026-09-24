# Decisions

Recorded 2026-09-10. This repository implements a personal setup, with platform differences made explicit.

| Decision | Status | Choice |
|---|---|---|
| Distribution | Confirmed by owner | Public GitHub repository |
| Bootstrap syntax | Confirmed by owner | One short command per OS is acceptable |
| Terminal | Confirmed by owner | Ghostty on macOS/Linux; WezTerm on native Windows |
| Workspace | Confirmed by owner | Herdr throughout, including native Windows |
| Theme | Requested family; initial flavor chosen | Catppuccin Mocha, mauve accents; Latte can follow |
| Agent | Proposed by supplied plan | OMP primary; other authenticated agents optional |
| Shell | Provisional | Preserve bash/zsh; PowerShell on Windows; do not change login shell |
| Package manager | Provisional | Homebrew for Unix CLI tools; WinGet on Windows |
| Runtime | First implementation | Python 3.9+ standard library for shared installer logic |
| File explorer | Provisional | Yazi as a normal Herdr pane; no third-party plugin |
| Editor | Confirmed by owner; Fresh pending Phase 0 qualification | Fresh as the managed default on macOS, chosen for familiar (non-modal) interaction and built-in review tools; Yazi and `fe` route into it through the generated `dev-edit` bridge. Linux/Windows keep their existing editor and are experimental |
| Pane zoom gesture | Implemented by default on macOS | Hammerspoon gesture bridge presses Herdr `ctrl+alt+shift+f1`/`f2` bindings (Ghostty cannot encode F13/F14); Linux/Windows intentionally have no bridge |
| Workspace layout | Provisional; code layout opt-in | Classic layout stays the default and is never rebuilt under a running workspace. `dev open . --layout code` adds the editor pane only on a qualified platform with Fresh installed; otherwise it reports `CODE LAYOUT UNAVAILABLE` and keeps the classic workspace |
| Editor settings ownership | Implemented | `editor.json` and Fresh's `config.json` are create-only like OMP's config, so UI or hand edits survive setup, `dev-update` and `--force-config` |
| Startup | Provisional | Explicit `dev` function; normal terminal remains usable |
| Memory | Provisional | Off initially; evaluate OMP built-in memory before Mem0 |
| Code graph | Provisional | Graphify opt-in, project-specific, after a benchmark |
| SSH | Conservative default | System OpenSSH, existing config, unchanged authentication |
| Ownership | Implemented | Create absent files; update only unmodified project-owned files |

The supplied AI plan is input to review, not an instruction authority. Its blanket approval gate is not adopted. The owner's request authorizes repository creation and beginning implementation. Tool choices marked provisional can be changed without restructuring the bootstrap.

## Remaining decisions

1. Which Linux distributions and CPU architectures must receive clean-machine tests? Proposed first target: Ubuntu 24.04 x86-64; macOS arm64; Windows 11 x86-64.
2. Which languages need LSP/debug adapters? The plan confirms all nine requested languages (Go, Python, Java, JavaScript, TypeScript, C++, C#, Rust, Bash) as in-scope for macOS across eight packs. `dev editor languages install` still refuses until the runtimes, versions and package sources for those packs are pinned and tested; the open question is whether to provision them per project through mise instead of a shared managed prefix.
3. Is Fresh the final editor? Phase 0 qualification has not been performed — Fresh is not installed here and network access was unavailable — so the recommendation is unconfirmed against a real release. If save/conflict safety or the required language capabilities fail on macOS, the Neovim alternative is evaluated against the owner's familiar-IDE preference instead of silently switching to a modal workflow.
4. Is local shell-history capture desirable? Atuin is an optional profile, with no sync account or AI feature enabled by this project.
5. Should persistent memory be enabled after comparing OMP local summaries and Mnemopi on one real repository?
6. Which remote host can be used for an interactive SSH/YubiKey acceptance test?
