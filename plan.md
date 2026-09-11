# AI Developer Cockpit — Feasibility, Design, Implementation, and Verification Plan

> **Purpose:** This document is intended to be handed directly to a Codex agent (or another capable coding agent) as the implementation brief.
>
> **Primary rule:** **Do not start implementation immediately.** First perform a complete feasibility pass across the entire proposed stack, identify blockers and incompatibilities, present findings, then ask the user the decision questions in this document with sensible defaults. Only implement after the user accepts the defaults or supplies alternatives.

---

## 0. Implementation Status — Current Snapshot

> Live status overlay. Sections 1–24 below are the original design brief; this section records what has actually been built as of the latest milestone and what remains open. Companion docs: `docs/feasibility.md`, `docs/decisions.md`, `docs/validation.md`, `docs/security.md`, `docs/customization.md`, `docs/intelligence.md`, `docs/themes.md`, `docs/mobile-access.md`.

### Done (implemented, tested, documented)

- **Unified CLI** — `dev_cockpit/cli.py` provides setup flags (`--install`, `--apply-config`, `--activate-shell`, `--uninstall-config`, `--doctor`, `--dry-run`, `--profile`, `--platform`, `--home`) and subcommands `launch`, `doctor`, `update`, `uninstall`, `completions`, `mobile`, `memory`, `graph`, `open`. `bootstrap/cockpit.py` is a thin shim.
- **Install-by-default** — a no-flag install provisions `core`, `cockpit` (herdr + OMP), and `terminal` (Ghostty/WezTerm + Nerd Font). `history` and `extras` remain opt-in profiles.
- **One-command install per OS** — `README.md` documents a `curl | sh` one-liner (macOS/Linux) and a PowerShell `Invoke-RestMethod` scriptblock (Windows), exercised by the CI install smoke test on all three OSes.
- **Auto-provisioning** — launchers install Python when missing (Homebrew on macOS, apt/dnf/pacman on Linux, WinGet on Windows); installs are idempotent with a `--dry-run` preview and a `--doctor` check.
- **Shell integration** — `config/shell/init.sh` / `init.ps1` add managed activation blocks and define `dev`, `dev-doctor`, `dev-update`, `dev-completions`, `dev-memory`, `dev-graph`, etc.
- **Completions** — shell completion scripts (gh, herdr, omp, starship) are generated automatically during initial install into `~/.config/dev-cockpit/completions/<shell>/` and auto-loaded on startup; `dev-completions` is a manual refresh tool.
- **Runtime deploy (one-liner)** — piped / `curl | sh` installs persist a content-addressed copy of the cockpit runtime so `dev` keeps working after the installer exits; local-clone installs keep using the live checkout.
- **Ownership/safety** — configuration is ownership-ledger based: only unchanged project-owned files are updated/removed, user-edited files are preserved, symlink/reparse targets are rejected, and an exclusive per-home `configuration.lock` refuses concurrent setup.
- **CLI tooling** — manifest-driven (`manifests/tools.json`, `manifests/downloads.json`) install of git, gh, rg, fd, fzf, zoxide, lazygit, delta, yazi, atuin, starship, mise, direnv, btop, plus herdr/OMP and terminals.
- **Themes** — Catppuccin Mocha vendored across terminals/CLI tools; alternative-theme links in `docs/themes.md`.
- **Docs** — `README.md`, `docs/feasibility.md`, `docs/decisions.md`, `docs/validation.md`, `docs/security.md`, `docs/customization.md`, `docs/intelligence.md`, `docs/themes.md`, `docs/mobile-access.md`.
- **Tests** — `python3 -m unittest discover -s tests` → **131 tests, OK (5 skipped)**; shell syntax checks pass (`sh -n bootstrap/setup.sh`, `bash -n config/shell/init.sh`).
- **Delivery** — branch `feat/dev-cockpit-cli-install-by-default`; PR #1 open.

### Deferred / not yet implemented (open work)

- **Remote development** — Herdr remote-machine workflow, SSH config integration, and YubiKey touch-policy validation are not implemented. System OpenSSH config is untouched and never silently weakened.
- **Global memory (Mem0)** — deferred by design (`docs/decisions.md` — "Off initially; evaluate OMP built-in memory before Mem0"). Current memory/graph are per-project and opt-in: `dev-memory` (OMP local memory + notes) and `dev-graph` (local Graphify code graph).
- **OMP advanced capabilities** — LSP/DAP validation, browser tooling, web search, subagent delegation, plugins — not yet validated end-to-end.
- **Clean-machine E2E** — CI runs an install smoke test on the published one-liner; a full clean-machine E2E matrix across all three OSes is not yet established.
- **Signed release bundles** — versioned, publisher-signed release bundles remain an open milestone (`docs/security.md`).
- **`docs/architecture.md` and `docs/troubleshooting.md`** — referenced by the brief but not yet authored.

---

## 1. Desired End State

Build a reproducible, cross-platform AI-first developer environment whose source of truth is a single Git repository.

The desired day-to-day experience is:

1. Open a terminal.
2. The preferred terminal environment starts or makes the developer cockpit immediately available.
3. Herdr is the workspace/agent orchestration layer.
4. Oh My Pi (`omp`) is the primary coding agent, with optional additional agents such as Codex and Claude Code.
5. The workspace provides an integrated file-navigation experience, ideally via a Herdr-compatible file-tree or Yazi pane.
6. Local and remote development machines can be managed from the same workflow.
7. Long-term agent memory and codebase knowledge can be enabled in a controlled, optional way.
8. Core command-line developer tooling is installed and configured consistently.
9. The whole environment is reproducible on macOS, Linux, and Windows.
10. A new machine can be bootstrapped from one public command, with a strong preference for a **single-line `curl` entrypoint**.
11. Installation is idempotent, testable, reversible where practical, and safe with respect to user files and credentials.

The implementation should prioritize reliability, debuggability, security, and maintainability over maximum plugin count.

---

## 2. Proposed Stack to Validate

The feasibility phase must validate every item below against its current upstream documentation, supported platforms, installation methods, configuration format, licensing, and integration model.

### 2.1 Terminal layer

Preferred candidates:

- **macOS:** Ghostty
- **Windows:** WezTerm or Windows Terminal
- **Linux:** Ghostty or WezTerm depending on support and packaging

The implementation should not require the same terminal emulator on every OS unless that meaningfully simplifies the system.

### 2.2 Workspace / agent runtime

- **Herdr** as the workspace, pane, agent, and remote-machine orchestration layer.
- Confirm how Herdr persists sessions, configures agents, manages remote connections, and loads plugins.

### 2.3 Primary coding agent

- **Oh My Pi / OMP** as the primary coding agent.
- Optional support for:
  - OpenAI Codex
  - Claude Code
  - other Herdr-compatible agents

Validate OMP support for:

- LSP
- debugger / DAP
- browser tooling
- web search
- subagents / task delegation
- MCP
- skills
- hooks
- rules / project instructions
- plugins / extensions
- persistent memory integrations

### 2.4 Memory and code knowledge

Candidates:

- **Mem0** for persistent semantic agent memory.
- **Graphify** for repository/codebase knowledge graph functionality.

These integrations should be optional unless their current stability, installation model, privacy model, and agent integrations are clearly mature.

Do **not** use Obsidian as the primary machine memory store. Obsidian may be supported later as a human-facing notes surface, but it should not be required for the core environment.

### 2.5 File navigation

Preferred order:

1. A stable Herdr-native/project-file-tree plugin if one exists and is trustworthy.
2. Yazi integrated into a Herdr pane.
3. Plain Yazi as a fallback.

The user wants a Warp-like experience where the project tree can remain visible beside the agent session.

### 2.6 CLI developer tools

Baseline candidates:

- git
- GitHub CLI (`gh`)
- ripgrep (`rg`)
- fd
- fzf
- zoxide
- lazygit
- delta
- yazi
- atuin
- starship
- mise
- direnv
- btop (optional)

The feasibility phase should remove redundant tools where appropriate and identify native Windows caveats.

### 2.7 Remote development

- Herdr remote-machine / SSH support.
- Existing SSH configuration should be respected.
- YubiKey-backed SSH must **not** be weakened or bypassed silently.
- If automation cannot work with mandatory touch-based authentication, clearly explain the alternatives rather than weakening security.

---

## 3. Non-Negotiable Implementation Principles

The implementation must follow these principles.

### 3.1 Feasibility before coding

No code changes before completing the feasibility report in Section 4.

### 3.2 Source of truth in Git

All non-secret configuration owned by this project should live in the repository.

Avoid hidden manual setup that cannot be recreated.

### 3.3 Idempotency

Running setup repeatedly must be safe.

The installer should:

- detect what is already installed;
- avoid destructive overwrites;
- update managed config safely;
- preserve unrelated user configuration;
- make repeat runs converge toward the desired state.

### 3.4 Explicit ownership

Every file created or modified by the installer should have a documented ownership strategy.

Prefer one of:

- project-owned config file referenced from a user's existing config;
- small clearly-delimited managed blocks;
- symlinks to repo-managed files where portable and safe;
- generated config under an application-specific config directory.

Avoid replacing entire user dotfiles unless the user explicitly chooses that mode.

### 3.5 Security first

Never:

- commit tokens, credentials, private SSH keys, API keys, or personal secrets;
- disable YubiKey requirements without explicit user approval;
- execute unauthenticated remote content without verification where a safer pattern is practical;
- indiscriminately install untrusted plugins.

### 3.6 Cross-platform by design

macOS, Linux, and native Windows are first-class targets.

WSL may be supported as an additional Windows mode, but it must not be the only supported Windows experience unless feasibility proves native Windows is impossible for a critical dependency.

### 3.7 Test the installer like production code

The bootstrap system is the product. It needs unit, integration, and end-to-end tests.

---

# 4. Phase 0 — Mandatory Feasibility Investigation

Before implementation, produce a written feasibility report and stop for user input.

For each component, verify the following from current upstream sources.

## 4.1 Component feasibility matrix

Create a table with at least these columns:

| Component | macOS | Linux | Windows native | WSL | Install method | Config location | Headless-safe | Current maturity | Risks | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|

Evaluate:

- Ghostty
- WezTerm
- Windows Terminal
- Herdr
- OMP
- Codex
- Claude Code
- Mem0
- Graphify
- Yazi
- Atuin
- Starship
- mise
- direnv
- ripgrep
- fd
- fzf
- lazygit
- delta
- GitHub CLI
- any proposed Herdr plugins
- any proposed OMP plugins, skills, MCP servers, hooks, or extensions

## 4.2 Validate Herdr architecture

Confirm:

- supported OSes;
- terminal requirements;
- plugin installation mechanism;
- plugin trust/security model;
- config file format and paths;
- ability to create persistent workspace layouts;
- ability to open OMP automatically;
- remote-machine workflow;
- SSH behavior and SSH config compatibility;
- whether Herdr can restore sessions cleanly after reboot;
- whether a file explorer can be pinned in the desired layout;
- whether panes/layouts are declarative or must be bootstrapped imperatively.

If a desired capability is not natively supported, propose the simplest maintainable alternative.

## 4.3 Validate OMP architecture

Confirm:

- current canonical repository/project;
- install mechanism;
- supported OSes;
- config format and precedence;
- LSP support and language-server discovery;
- DAP/debugger support;
- browser integration;
- web-search support;
- agent/subagent support;
- project rules/instructions;
- skill/plugin system;
- MCP compatibility;
- hook lifecycle;
- memory extension points;
- compatibility with Mem0;
- compatibility with Graphify;
- whether external tool definitions materially inflate context or startup time;
- secrets/config handling.

## 4.4 Validate Mem0

Determine whether Mem0 should be:

- enabled by default;
- installed but disabled;
- an optional post-install feature;
- omitted initially.

Verify:

- local vs hosted operation;
- authentication requirements;
- data retention and privacy implications;
- project-scoped vs global memory;
- compatibility with OMP;
- failure behavior when unavailable;
- uninstall/disable path.

## 4.5 Validate Graphify

Determine whether Graphify provides enough value and maturity to justify default installation.

Verify:

- current install method;
- local storage requirements;
- supported languages;
- indexing cost/time;
- repository-size constraints;
- OMP/MCP integration;
- re-index/update strategy;
- privacy model;
- Windows support;
- failure behavior.

## 4.6 Validate the file-tree UX

Evaluate current choices for the requested Warp-like project tree.

Rank:

1. Herdr-native tree/plugin.
2. Yazi-in-Herdr.
3. Alternative terminal file manager.

Assess:

- stability;
- plugin provenance;
- maintenance activity;
- keyboard control;
- clickable/open-file integration;
- git status decorations;
- follow-current-directory behavior;
- Windows support.

## 4.7 Validate remote SSH and YubiKey constraints

The report must specifically test the architecture against YubiKey-backed SSH.

Determine:

- whether Herdr uses the system SSH client or a separate implementation;
- whether it respects `~/.ssh/config`;
- whether SSH connection multiplexing can reduce repeated touches;
- whether native SSH agent integration is available on macOS/Linux/Windows;
- how FIDO2 touch requirements interact with persistent sessions;
- whether a separate restricted automation key is a reasonable optional pattern;
- whether there is a secure way to support unattended remote agents without weakening the human login policy.

**Do not implement a workaround that bypasses required user presence.**

## 4.8 Validate one-line cross-platform bootstrap feasibility

This needs explicit investigation.

The desired UX is conceptually:

```text
curl <stable-url> | <something>
```

The challenge is that macOS/Linux normally use POSIX shells while native Windows commonly uses PowerShell. A single identical command may not be possible without one of the following:

- a carefully designed polyglot launcher;
- a portable runtime already present on all targets;
- a downloaded native bootstrap executable;
- a first-stage script that detects the environment and dispatches safely;
- accepting two documented one-liners while preserving a single canonical setup URL.

The agent must investigate this completely and present the user with:

- **Option A — preferred:** truly identical command on macOS, Linux, and native Windows, if robustly feasible;
- **Option B — sensible fallback:** one canonical setup URL with tiny OS-specific invocation syntax;
- **Option C — WSL-based Windows path:** only as an optional alternative, not the default unless native Windows support is blocked.

Do not fake cross-platform support by requiring Git Bash or WSL without saying so.

## 4.9 Feasibility report output

Before coding, present:

1. Executive summary.
2. Feasibility matrix.
3. Confirmed blockers.
4. Components that should be optional rather than default.
5. Security concerns.
6. Cross-platform bootstrap conclusion.
7. Recommended architecture.
8. Questions from Section 5.

Then wait for the user's answers or explicit acceptance of defaults.

---

# 5. User Decision Questions — Ask Only After Feasibility

Ask the user the questions below after completing the feasibility pass. Each question must contain a recommended default.

Do not overwhelm the user with implementation trivia. Group questions logically and offer an **“accept all recommended defaults”** option.

## 5.1 Terminal preference

**Question:** Which terminal strategy should be used?

Recommended default:

- macOS: Ghostty
- Linux: Ghostty if stable/supported, otherwise WezTerm
- Windows: WezTerm or Windows Terminal based on feasibility

Options:

- A. OS-native best-of-breed terminals — **recommended**
- B. WezTerm everywhere for consistency
- C. Do not manage terminal emulator installation/configuration

## 5.2 Shell preference

Recommended default:

- macOS/Linux: zsh where already standard, otherwise preserve current shell and configure supported integrations
- Windows: PowerShell 7

Options:

- A. Preserve existing shell and augment it — **recommended**
- B. Standardize on zsh + PowerShell
- C. User-specified shell matrix

## 5.3 Herdr startup behavior

Recommended default:

- Install Herdr and provide an easy `dev`/`cockpit` launcher.
- Do not make every new terminal process automatically enter Herdr unless the user chooses it.

Options:

- A. Dedicated `dev` command — **recommended**
- B. Launch Herdr automatically when terminal opens
- C. Manual launch only

## 5.4 OMP role

Recommended default:

- OMP is the primary coding agent.
- Codex and Claude Code integrations are optional adapters when already installed/authenticated.

Options:

- A. OMP primary + optional additional agents — **recommended**
- B. OMP only
- C. User chooses another primary agent

## 5.5 Memory

Recommended default:

- Mem0 installed as an optional feature but disabled until credentials/privacy settings are configured.

Options:

- A. Optional and disabled by default — **recommended**
- B. Enabled by default
- C. Do not install Mem0

## 5.6 Graphify

Recommended default:

- Optional component, installed only if current feasibility and cross-platform support are strong.

Options:

- A. Optional — **recommended**
- B. Default-on
- C. Omit

## 5.7 File explorer

Recommended default:

- Use the most stable Herdr-native file-tree solution if trustworthy; otherwise Yazi in a pinned pane.

Options:

- A. Best stable Herdr-native tree — **recommended if viable**
- B. Yazi pane — **fallback default**
- C. No persistent file tree

## 5.8 Remote hosts

Recommended default:

- Import/use existing SSH config without copying private keys.
- Do not automatically provision remote credentials.

Options:

- A. Respect existing SSH config only — **recommended**
- B. Add project-managed SSH host stanzas
- C. Skip remote support initially

## 5.9 YubiKey policy

Recommended default:

- Preserve current YubiKey authentication policy.
- Optimize connection reuse if supported.

Options:

- A. Preserve touch requirement — **recommended**
- B. Add a separate restricted automation identity for selected hosts
- C. User-specified policy

## 5.10 Dotfile ownership

Recommended default:

- Non-destructive managed snippets / include files rather than replacing entire dotfiles.

Options:

- A. Managed includes/snippets — **recommended**
- B. Symlink full dotfiles from repo
- C. Generate config but require manual activation

## 5.11 Installation scope

Recommended default:

- Install core CLI tools automatically.
- Prompt/skip optional AI services requiring account authentication.

Options:

- A. Core automatic + optional integrations — **recommended**
- B. Everything automatic where technically possible
- C. Minimal bootstrap only

## 5.12 Telemetry and network services

Recommended default:

- Preserve upstream defaults but clearly report them.
- Do not enable additional project telemetry.

Options:

- A. No project telemetry — **recommended**
- B. User-selected telemetry settings

## 5.13 Windows mode

Recommended default:

- Native PowerShell/Windows support first, WSL optional.

Options:

- A. Native Windows + optional WSL — **recommended**
- B. WSL-first
- C. Native Windows only

## 5.14 Installer command style

Recommended default:

- Pursue a single identical one-liner only if feasibility proves it safe and maintainable.
- Otherwise use one canonical URL with two tiny OS-specific invocation forms.

Options:

- A. Safety/reliability over literal identical syntax — **recommended**
- B. Identical command is a hard requirement

---

# 6. Target Repository Structure

The exact structure may change after feasibility, but aim for something close to:

```text
dev-environment/
├── README.md
├── plan.md
├── LICENSE
├── .editorconfig
├── .gitignore
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── installer-e2e.yml
│       ├── security.yml
│       └── release.yml              # only if releases are needed
├── bootstrap/
│   ├── setup                       # public first-stage launcher or polyglot entrypoint
│   ├── setup.sh
│   ├── setup.ps1
│   ├── common/
│   │   ├── manifest.*
│   │   ├── detect.*
│   │   ├── install.*
│   │   └── config.*
│   └── uninstall/
│       ├── uninstall.sh
│       └── uninstall.ps1
├── config/
│   ├── herdr/
│   ├── omp/
│   │   ├── rules/
│   │   ├── skills/
│   │   ├── agents/
│   │   ├── hooks/
│   │   └── mcp/
│   ├── shell/
│   ├── starship/
│   ├── atuin/
│   ├── yazi/
│   ├── git/
│   └── terminals/
│       ├── ghostty/
│       └── wezterm/
├── lib/
│   ├── manifest/
│   ├── platform/
│   ├── installers/
│   ├── config/
│   ├── backup/
│   └── validation/
├── manifests/
│   ├── core-tools.*
│   ├── optional-tools.*
│   └── platform-overrides.*
├── scripts/
│   ├── dev
│   ├── verify
│   ├── doctor
│   ├── update
│   └── test
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── e2e/
│       ├── macos/
│       ├── linux/
│       └── windows/
└── docs/
    ├── architecture.md
    ├── feasibility.md
    ├── security.md
    ├── customization.md
    ├── troubleshooting.md
    └── remote-development.md
```

Prefer data-driven package manifests over giant duplicated shell scripts.

---

# 7. Implementation Architecture

## 7.1 Bootstrap stages

Use a staged installer.

### Stage 0 — tiny public launcher

Responsibilities:

- determine OS/shell/runtime;
- establish secure temporary directory;
- fetch the versioned installer bundle or repository snapshot;
- verify checksum/signature if the distribution model supports it;
- invoke the correct platform implementation;
- surface readable errors.

It should contain almost no business logic.

### Stage 1 — platform bootstrap

Responsibilities:

- package-manager discovery/install if appropriate;
- install prerequisites;
- clone or fetch the configuration repository;
- invoke shared orchestration logic.

### Stage 2 — declarative tool installation

Install tools from a manifest with fields such as:

```text
name
required/optional
macOS package
Linux package(s)
Windows package
binary verification command
minimum version
config handler
```

### Stage 3 — configuration

Apply managed configuration non-destructively.

### Stage 4 — integration setup

Configure:

- Herdr
- OMP
- file explorer
- terminal launcher
- optional memory/knowledge integrations
- remote host integration

### Stage 5 — verification

Run a `doctor` command and print a concise report.

---

# 8. Package Manager Strategy

Feasibility should determine the final matrix, but the expected direction is:

## macOS

Preferred:

- Homebrew for external CLI packages where appropriate.
- Official install methods where upstream strongly recommends them.

## Linux

Do not assume one distribution.

Support a documented set such as:

- Debian/Ubuntu
- Fedora
- Arch, if practical

Prefer:

- official packages when sufficiently current;
- upstream release binaries when distro versions are unsuitable;
- mise for language/runtime management where helpful.

Unknown distros should fail gracefully with manual instructions, not guess.

## Windows

Preferred package managers to evaluate:

- winget
- Scoop

Use the smallest number of package managers possible.

Do not require Chocolatey unless there is a concrete reason.

---

# 9. Shell and Environment Integration

The installer must avoid destroying `.zshrc`, `.bashrc`, PowerShell profiles, etc.

Prefer managed include files.

Example conceptual pattern:

```text
~/.config/dev-cockpit/shell.zsh
```

and add one idempotent line to the user's shell config:

```text
source ~/.config/dev-cockpit/shell.zsh
```

Windows should use the PowerShell equivalent.

Managed shell integrations may include:

- Starship init
- zoxide init
- Atuin init
- fzf integration
- direnv hook
- aliases/functions such as `dev`, `doctor`, and `dev-update`

Keep aliases conservative and avoid overriding standard commands.

---

# 10. Herdr Configuration

After feasibility confirms current APIs/configuration:

Create a default developer workspace with roughly this UX:

```text
┌─────────────────────────────────────────┐
│ Projects / Agents / Remote machines     │
├─────────────────────┬───────────────────┤
│                     │                   │
│      OMP agent      │    File tree      │
│                     │                   │
├─────────────────────┴───────────────────┤
│ shell / tests / logs / secondary agent  │
└─────────────────────────────────────────┘
```

Requirements:

- OMP should be easy to start in the active project.
- A file explorer should be one command/key away or persist in layout.
- A normal shell pane should always be available.
- Remote machines should be clearly distinguishable from local sessions.
- Layouts should restore cleanly where Herdr supports restoration.
- Key bindings should avoid collisions and be documented.

Do not install large numbers of third-party Herdr plugins by default.

Every plugin must have a provenance/trust review.

---

# 11. OMP Configuration

Configure OMP conservatively and modularly.

## 11.1 Default capabilities

Enable where mature and available:

- LSP
- DAP/debugging
- web search
- browser tooling
- subagents/tasks
- project skills
- project rules
- hooks
- MCP

## 11.2 Project rules

Create reusable rules such as:

- coding style
- testing expectations
- security expectations
- Git hygiene
- dependency policy
- documentation policy
- definition of done

## 11.3 Skills

Start with a small, high-value set such as:

- investigate-bug
- implement-feature
- review-pr
- write-tests
- refactor-safely
- security-review
- release-check
- dependency-upgrade

Do not create dozens of speculative skills.

## 11.4 Agents/subagents

Possible initial profiles:

- researcher
- implementer
- reviewer
- tester

Only include these if OMP's current agent model makes them useful without excessive complexity.

## 11.5 MCP policy

Default MCP integrations should be minimal.

Potential defaults:

- GitHub
- one memory provider if enabled
- one code knowledge provider if enabled
- one browser/search capability if not already built in

Avoid a large tool registry that inflates startup/context overhead.

---

# 12. Mem0 and Graphify Integration Strategy

## 12.1 Mem0

Treat memory as an explicit capability with clear user control.

Requirements:

- user can enable/disable it;
- credentials are stored using platform-appropriate secret mechanisms or environment configuration, never committed;
- project memory and personal/global memory must be distinguishable if supported;
- failure of Mem0 must not prevent OMP from starting;
- `doctor` should report whether memory is configured and reachable.

## 12.2 Graphify

Treat code graphing as an optional enhancement unless feasibility demonstrates low cost and strong value.

Requirements:

- index only repositories explicitly selected or opened;
- avoid indexing secrets/generated directories where configurable;
- provide refresh/update commands;
- do not make OMP startup depend on Graphify availability;
- report resource usage and storage locations in docs.

---

# 13. Remote Development and SSH

## 13.1 Preserve existing SSH config

Prefer consuming the user's current SSH configuration.

Do not copy private keys into this repository.

## 13.2 YubiKey

The implementation must not silently weaken YubiKey-backed security.

If a physical touch is required, support one or more of:

- persistent SSH connection reuse;
- ControlMaster / multiplexing if compatible and user-approved;
- native SSH-agent integration;
- optional restricted automation identity for selected hosts.

Document threat model and trade-offs.

## 13.3 Automation identity, if chosen

If the user opts into unattended remote automation:

- use a separate key/identity;
- restrict server-side permissions where possible;
- avoid broad production access;
- support easy revocation;
- document rotation.

---

# 14. Installer Requirements

The bootstrap installer is a critical deliverable.

## 14.1 One-line UX

Target a public stable endpoint such as conceptually:

```text
https://<host>/setup
```

The exact command depends on feasibility.

Do not advertise one identical command until it has passed native tests on:

- clean macOS
- clean Linux
- clean Windows PowerShell

## 14.2 Safety

The installer must:

- use strict error handling;
- validate downloads;
- avoid `sudo` unless necessary;
- explain privilege prompts;
- create backups before modifying existing config;
- never overwrite SSH keys;
- never overwrite unrelated user files;
- be interrupt-safe where possible;
- return non-zero on failure;
- print actionable remediation.

## 14.3 Modes

Support flags/modes if practical:

```text
--dry-run
--yes
--minimal
--full
--no-terminal
--no-ai-extras
--no-remote
--unattended   # only for non-secret, safe automation
```

Windows equivalents should preserve semantics.

## 14.4 Idempotency

Required test:

1. Run setup on a clean machine.
2. Run it again.
3. Assert no destructive changes and no duplicate shell/profile entries.

## 14.5 Update path

Provide a stable command such as:

```text
dev-update
```

or equivalent.

Updates should:

- pull project configuration;
- apply migrations;
- update managed tools based on explicit policy;
- avoid unexpectedly upgrading everything on every shell startup.

## 14.6 Doctor command

Provide:

```text
dev-doctor
```

or equivalent.

It should validate:

- OS support
- shell integration
- package manager
- Git
- Herdr
- OMP
- terminal integration
- core CLIs
- optional integrations
- SSH availability
- config ownership
- stale/broken symlinks
- path ordering
- version mismatches

Output should be readable and actionable.

---

# 15. Testing Strategy

The project should have **a lot of tests**, especially around installer behavior.

Tests must cover successful paths and failure paths.

## 15.1 Unit tests

Unit-test pure logic such as:

- OS detection
- architecture detection
- package-manager selection
- manifest parsing
- version comparison
- command construction
- config block insertion/removal
- path normalization
- backup naming
- tool presence detection
- feature flag resolution
- shell detection
- SSH config parsing where implemented
- URL/checksum verification helpers

Aim for high coverage of business logic, not meaningless line coverage.

## 15.2 Integration tests

Test against real shells/package managers in controlled environments.

Examples:

- managed `.zshrc` insertion
- managed PowerShell profile insertion
- repeated configuration application
- backup/restore
- mock package installations
- failure recovery
- `doctor` against intentionally broken environments
- configuration generation for Herdr/OMP

## 15.3 End-to-end tests

E2E tests should run in clean environments as close to real machines as CI permits.

### Linux

Use containers and/or VMs for at least:

- Ubuntu LTS
- one additional supported distro if claimed

### macOS

Use macOS CI runners.

Test:

- bootstrap from clean home directory
- Homebrew path variations where possible
- shell integration
- idempotent rerun
- doctor
- uninstall/rollback path

### Windows

Use native Windows CI runners, not only WSL.

Test in PowerShell.

Validate:

- package-manager discovery
- PATH handling
- profile modification
- line endings
- filesystem path quoting
- idempotency
- doctor
- uninstall/rollback

## 15.4 Golden tests

Where configuration generation is deterministic, maintain golden fixtures for:

- Herdr config
- OMP config
- shell snippets
- terminal config fragments

## 15.5 Destructive-behavior tests

Explicitly verify the installer does **not**:

- erase user dotfiles;
- duplicate source/import lines;
- modify private SSH keys;
- overwrite unrelated config sections;
- write secrets into repository files;
- require elevated privileges unnecessarily.

## 15.6 Failure injection

Test scenarios such as:

- no network
- package manager unavailable
- download checksum mismatch
- GitHub unavailable
- unsupported OS
- partial previous installation
- read-only config file
- missing HOME
- PATH conflict
- Herdr install failure
- OMP install failure
- optional Mem0 failure
- optional Graphify failure

Core shell usability should survive optional component failures.

## 15.7 Bootstrap-from-URL E2E test

The public one-line installation path itself must be tested.

CI should fetch exactly the published entrypoint URL and execute the documented command on each supported OS.

Do not only test internal scripts directly.

---

# 16. CI Workflow

Create CI even if a formal release workflow is unnecessary.

Minimum CI should include:

- formatting/linting
- unit tests
- integration tests
- shell linting (`shellcheck` where applicable)
- PowerShell static analysis where useful
- secret scanning
- dependency/security scanning appropriate to implementation language
- Linux E2E
- macOS E2E
- native Windows E2E

Avoid making CI depend on real user API keys.

Mock optional external services.

---

# 17. Release Workflow

A formal release pipeline may not be necessary initially.

## Recommended default

Use the repository's default branch as the configuration source during development, but design the installer so it can later pin versions/tags.

If the bootstrap endpoint distributes immutable binaries or versioned bundles, then add releases.

If a release workflow is needed, it should:

1. run the full test matrix;
2. create a version tag;
3. produce platform bootstrap artifacts if applicable;
4. generate checksums;
5. optionally sign artifacts;
6. publish release notes;
7. update the stable bootstrap pointer only after all tests pass.

Do not build a complex release system until the distribution model actually requires it.

---

# 18. Rollback / Uninstall

Provide a documented uninstall path.

It should remove only project-owned changes.

Requirements:

- remove managed shell/profile blocks;
- remove project-owned generated config;
- restore backups when safe and unambiguous;
- leave unrelated user settings untouched;
- leave user projects untouched;
- optionally remove installed CLI tools only if the user explicitly asks;
- never delete shared package managers by default.

---

# 19. Documentation Deliverables

The implementation is not complete without docs.

At minimum:

## README.md

Include:

- what this project does;
- supported platforms;
- one-line install command(s);
- quick start;
- how to launch the cockpit;
- how to update;
- how to run doctor;
- how to uninstall;
- security note.

## docs/feasibility.md

The initial feasibility investigation and decisions.

## docs/architecture.md

Explain:

- component boundaries;
- bootstrap stages;
- config ownership;
- why each major tool exists;
- optional vs required components.

## docs/security.md

Cover:

- remote code execution implications of curl installers;
- checksum/signature model;
- plugin trust;
- secrets;
- SSH/YubiKey;
- optional AI service data handling.

## docs/customization.md

Show how to:

- replace terminal emulator;
- disable Mem0;
- disable Graphify;
- switch file explorer;
- add/remove OMP skills;
- add remote machines;
- override tool lists per OS.

## docs/troubleshooting.md

Common failures with remediation.

---

# 20. Security Review Checklist

Before declaring completion, review:

- [ ] No secrets committed.
- [ ] Installer downloads are HTTPS-only.
- [ ] Download integrity strategy documented.
- [ ] Third-party plugin list minimized.
- [ ] Plugin provenance reviewed.
- [ ] Installer does not silently disable security controls.
- [ ] YubiKey behavior preserved unless user chose otherwise.
- [ ] Optional AI services fail open with respect to developer shell usability.
- [ ] No hidden persistent daemons unless explicitly needed/documented.
- [ ] No unexpected telemetry added by this project.
- [ ] Config permissions are appropriate.
- [ ] Temp files are handled safely.
- [ ] Shell argument quoting tested on paths containing spaces.
- [ ] Windows execution-policy implications documented.

---

# 21. Definition of Done

The project is done only when all of the following are true.

## Feasibility

- [ ] Every proposed stack component has been evaluated against current upstream documentation.
- [ ] Unsupported or unstable components have been downgraded to optional or removed.
- [ ] User decisions are recorded.

## macOS

- [ ] Fresh-machine bootstrap succeeds.
- [ ] Core CLI stack installs.
- [ ] Herdr works.
- [ ] OMP works.
- [ ] file navigation works.
- [ ] rerunning installer is safe.
- [ ] doctor passes.

## Linux

- [ ] Fresh-machine bootstrap succeeds on every claimed distro.
- [ ] Core CLI stack installs.
- [ ] Herdr works where claimed.
- [ ] OMP works.
- [ ] file navigation works.
- [ ] rerunning installer is safe.
- [ ] doctor passes.

## Windows native

- [ ] Fresh-machine bootstrap succeeds from PowerShell.
- [ ] Core CLI stack installs.
- [ ] Herdr works where claimed.
- [ ] OMP works.
- [ ] file navigation works.
- [ ] rerunning installer is safe.
- [ ] doctor passes.

## Remote

- [ ] Existing SSH config can be used.
- [ ] YubiKey policy is not silently weakened.
- [ ] Remote workflow is documented.

## Installer

- [ ] Public bootstrap URL exists.
- [ ] Documented one-line command(s) are actually exercised in CI.
- [ ] Installer is idempotent.
- [ ] Installer has dry-run or equivalent preview if practical.
- [ ] Failures produce actionable messages.
- [ ] Uninstall/rollback path exists.

## Quality

- [ ] Unit tests cover installer business logic.
- [ ] Integration tests cover config mutation.
- [ ] E2E tests run on macOS, Linux, and Windows.
- [ ] CI is green.
- [ ] Security review checklist is complete.
- [ ] Documentation is complete.

---

# 22. Suggested Implementation Order

After feasibility and user approval, implement in this order.

## Milestone 1 — Repository foundation

- repo structure
- manifests
- test framework
- CI skeleton
- platform detection
- logging/error framework

## Milestone 2 — Core CLI bootstrap

Install and verify:

- Git
- GitHub CLI
- ripgrep
- fd
- fzf
- zoxide
- lazygit
- delta
- Yazi
- Atuin
- Starship
- mise
- direnv where supported

Add unit/integration tests before moving on.

## Milestone 3 — Shell/profile integration

- managed snippets
- prompt/history/navigation initialization
- `dev`, `dev-doctor`, `dev-update`
- idempotency tests

## Milestone 4 — OMP

- install
- configuration
- rules
- initial skills
- LSP/DAP validation
- optional extra-agent adapters

## Milestone 5 — Herdr

- install
- agent wiring
- default layout
- file-tree/Yazi integration
- session persistence

## Milestone 6 — Remote development

- SSH config integration
- Herdr remote workflow
- connection reuse evaluation
- YubiKey-safe behavior

## Milestone 7 — Optional intelligence layer

- Mem0
- Graphify

Each must remain removable/disableable.

## Milestone 8 — Public bootstrap endpoint

- stage-0 launcher
- integrity checks
- clean-machine E2E tests
- documentation

## Milestone 9 — Hardening

- failure injection
- security review
- uninstall/rollback
- full CI matrix
- docs polish

---

# 23. Instructions to the Implementing Codex Agent

Use the following operating rules while executing this plan.

1. **Start with research, not code.**
2. Verify current documentation and upstream support; do not rely on stale assumptions in this file.
3. Produce `docs/feasibility.md` before implementation.
4. Stop after feasibility and ask the user the grouped questions in Section 5.
5. Offer **“accept all recommended defaults”** as a valid response.
6. Record decisions in `docs/architecture.md` or an ADR-style decision log.
7. Implement incrementally in the order from Section 22.
8. Add tests alongside each subsystem, not at the end.
9. Never weaken SSH/YubiKey security without explicit approval.
10. Never commit credentials.
11. Favor declarative manifests over duplicated platform scripts.
12. Preserve existing user configuration and make all mutation idempotent.
13. Treat native Windows as a real target; do not quietly substitute WSL.
14. Exercise the exact documented bootstrap command in CI.
15. If the literal identical cross-platform `curl` command is not safely feasible, explain why and implement the safest closest alternative with one canonical setup URL.
16. Keep optional integrations optional: Mem0 or Graphify failure must not break the core developer environment.
17. Keep the default plugin/MCP surface small and auditable.
18. Provide clear progress updates as milestones are completed.
19. At the end, run the complete test matrix and `doctor` checks and summarize any remaining limitations honestly.

---

# 24. Final Product Vision

The repository should ultimately make a machine feel disposable.

A developer should be able to move to a new Mac, Linux workstation, or Windows machine, run the documented bootstrap command, authenticate only where genuinely necessary, and end up with the same practical developer cockpit:

```text
Terminal
  └── Herdr
      ├── OMP
      ├── optional Codex / Claude Code
      ├── project file tree / Yazi
      ├── shell / tests / logs
      └── local + remote workspaces

Supporting environment
  ├── Git + gh + lazygit + delta
  ├── rg + fd + fzf + zoxide
  ├── Atuin
  ├── Starship
  ├── mise + direnv
  ├── optional Mem0
  └── optional Graphify
```

The goal is not to recreate Warp feature-for-feature. The goal is to build a composable, reproducible, AI-first development environment that can be understood, tested, repaired, and recreated from source.
