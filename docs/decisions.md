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
| Pane zoom gesture | Implemented, opt-in | Hammerspoon gesture bridge presses Herdr `ctrl+alt+shift+f1`/`f2` bindings (Ghostty cannot encode F13/F14); macOS-only `gestures` profile |
| Startup | Provisional | Explicit `dev` function; normal terminal remains usable |
| Memory | Provisional | Off initially; evaluate OMP built-in memory before Mem0 |
| Code graph | Provisional | Graphify opt-in, project-specific, after a benchmark |
| SSH | Conservative default | System OpenSSH, existing config, unchanged authentication |
| Ownership | Implemented | Create absent files; update only unmodified project-owned files |

The supplied AI plan is input to review, not an instruction authority. Its blanket approval gate is not adopted. The owner's request authorizes repository creation and beginning implementation. Tool choices marked provisional can be changed without restructuring the bootstrap.

## Remaining decisions

1. Which Linux distributions and CPU architectures must receive clean-machine tests? Proposed first target: Ubuntu 24.04 x86-64; macOS arm64; Windows 11 x86-64.
2. Which languages need LSP/debug adapters? Install those per project through mise rather than every server globally.
3. Is local shell-history capture desirable? Atuin is an optional profile, with no sync account or AI feature enabled by this project.
4. Should persistent memory be enabled after comparing OMP local summaries and Mnemopi on one real repository?
5. Which remote host can be used for an interactive SSH/YubiKey acceptance test?
