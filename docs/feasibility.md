# Feasibility review

Reviewed 2026-09-10 against current upstream documentation and repository metadata. **Documentation support is not an end-to-end test result.** See [validation](validation.md) for what this repository has actually exercised.

## Findings that change the supplied plan

- The canonical Herdr repository is **herdrdev/herdr**, not the older SuperCodeAgents fork. Current stable documentation says native Windows is generally available even though its page slug remains `windows-beta`. Plugins are preview on Windows; Windows cannot be a remote target. Multi-machine views are not supported on Windows, while standalone remote attach to Unix hosts is. [Windows support](https://herdr.dev/docs/windows-beta/), [connecting machines](https://herdr.dev/docs/connecting-machines/)
- Atuin now has native Windows binaries and PowerShell integration. PowerShell is tier 2, with fewer features than bash/zsh. Old claims that it requires WSL are outdated. [Support matrix](https://docs.atuin.sh/latest/support/)
- OMP now includes LSP, DAP, browser/search, subagents, MCP, extension hooks, and several memory backends. A pile of redundant MCP servers would add complexity. [OMP](https://github.com/can1357/oh-my-pi), [memory](https://github.com/can1357/oh-my-pi/blob/main/docs/memory.md)
- Catppuccin has established ports for this stack. Use built-in themes or licensed pinned assets; do not fetch executable theme plugins during shell startup. [Ports](https://catppuccin.com/ports/)
- Stock Windows PowerShell and POSIX shells do not share a guaranteed interpreter. One command per OS is accepted by the owner. An identical `pwsh` or Python command is possible only after provisioning that runtime. A polyglot does not eliminate the interpreter problem. [PowerShell installation](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell)

## Component matrix

Y = upstream platform support; conditional = platform/version/dependency caveats; optional = not required for the initial setup. WSL follows Linux and is additional, not our native Windows substitute. Every CLI below is headless-capable; terminal applications require a graphical session. Agent authentication remains interactive or separately provisioned.

| Component / license | macOS | Linux / WSL | Native Windows | Install / config | Assessment |
|---|---|---|---|---|---|
| [Ghostty](https://ghostty.org/docs/install/binary) / MIT | Y | Y; packaging varies | No | macOS cask; Linux distro package; `~/.config/ghostty/config` | Chosen for Unix desktops. Linux installer adapter remains open. |
| [WezTerm](https://wezterm.org/installation.html) / MIT | Y | Y | Y | WinGet; `~/.wezterm.lua` | Chosen for Windows; Lua configuration, built-in splits. Do not assume its SSH engine equals system OpenSSH. |
| [Windows Terminal](https://github.com/microsoft/terminal) / MIT | No | No | Y | Store/WinGet; application `settings.json` | Valid fallback; not additionally managed. |
| [Herdr](https://github.com/herdrdev/herdr) / Apache-2.0 | Y | Y | Y, gaps above | brew/official binaries; Unix `~/.config/herdr/config.toml`, Windows `%APPDATA%/herdr/config.toml` | Chosen throughout; rapid development, pin/test integrations. |
| [OMP](https://github.com/can1357/oh-my-pi) / MIT | Y | Y; musl needs runtime libraries | Y | official binary, brew tap, or Bun; `~/.omp/agent/config.yml` | Proposed primary. Config and agent behavior change quickly. |
| [Codex](https://learn.chatgpt.com/docs/windows/windows-sandbox) / CLI Apache-2.0 | Y | Y | Y | official installer/package; `~/.codex/config.toml` | Optional existing authenticated agent; sandbox setup is platform-specific. |
| [Claude Code](https://code.claude.com/docs/en/setup) / proprietary product | Y | Y | Y; follow Git/shell prerequisites | official installer; `~/.claude/settings.json` | Optional; not installed or authenticated here. |
| [Mem0](https://docs.mem0.ai/open-source/overview) / OSS Apache-2.0 | conditional | conditional | conditional | Python/JS SDK; backend-specific config | SDK is not a complete standalone memory service. Defer. |
| [Graphify](https://github.com/Graphify-Labs/graphify) / Apache-2.0 | Y | Y | documented route | `uv tool install graphifyy`; per-repo `graphify-out/` | Optional; Python/extras and agent registration need testing. |
| [Yazi](https://yazi-rs.github.io/docs/installation/) / MIT | Y | Y | Y | brew/WinGet; Unix `~/.config/yazi`, Windows `%APPDATA%/yazi/config` | Core; previews need optional external tools and terminal support. |
| [Atuin](https://docs.atuin.sh/latest/guide/installation/) / MIT | Y | Y | Y, PowerShell tier 2 | brew/WinGet; platform config dir | Optional history capture. No sync account or import on bootstrap. |
| [Starship](https://starship.rs/) / ISC | Y | Y | Y | brew/WinGet; `STARSHIP_CONFIG` | Core prompt; Nerd Font needed for full preset glyphs. |
| [mise](https://mise.jdx.dev/installing-mise.html) / MIT | Y | Y | Y; backend support varies | brew/WinGet; `mise.toml` | Core for per-project runtimes. Avoid also managing the same runtime with another tool. |
| [direnv](https://direnv.net/docs/hook.html) / MIT | Y | Y | Hook exists; bash dependency caveats | package manager; `.envrc`, config dir | Optional Unix initially. Overlaps mise env; never auto-allow `.envrc`. |
| [Git](https://git-scm.com/downloads) / GPL-2.0 | Y | Y | Y | brew/WinGet; global and project Git config | Core; identity and SSH config untouched. |
| [GitHub CLI](https://github.com/cli/cli#installation) / MIT | Y | Y | Y | brew/WinGet; gh config/auth store | Core; login separately, no credentials in this repo. |
| [ripgrep](https://github.com/BurntSushi/ripgrep#installation) / MIT or Unlicense | Y | Y | Y | brew/WinGet; optional `RIPGREP_CONFIG_PATH` | Core, no config necessary. |
| [fd](https://github.com/sharkdp/fd#installation) / MIT or Apache-2.0 | Y | Y | Y | brew/WinGet; ignore files | Core; distro `fdfind` naming avoided through brew. |
| [fzf](https://github.com/junegunn/fzf#installation) / MIT | Y | Y | Y | brew/WinGet; shell options | Core binary; keyboard integration is shell-specific. |
| [zoxide](https://github.com/ajeetdsouza/zoxide#installation) / MIT | Y | Y | Y | brew/WinGet; shell init | Core; local navigation database. |
| [lazygit](https://github.com/jesseduffield/lazygit#installation) / MIT | Y | Y | Y | brew/WinGet; platform config dir | Core Git TUI; theming follow-up. |
| [delta](https://github.com/dandavison/delta#installation) / MIT | Y | Y | Y | brew/WinGet; Git config | Core binary; Git pager activation remains explicit. |
| [btop](https://github.com/aristocratos/btop) / Apache-2.0 | Y | Y | Different port | platform packages | Optional Unix only; no claim of identical Windows implementation. |
| Third-party Herdr/OMP plugins | depends | depends | depends | host-executed code | None selected. Registry presence does not establish trust. |

Package IDs in `manifests/tools.json` were checked against upstream WinGet paths and Homebrew metadata. Package-manager repositories supply current versions: **this prototype is not a fully locked binary environment**. Licenses above summarize upstream projects, not all transitive dependencies or hosted-service terms.

## Herdr: architecture and file navigation

Herdr owns pane processes in a background server. Detaching keeps those processes alive. Reboot/server shutdown stops them; snapshots restore layout, and supported agents can resume conversations. OMP integration version 3 reports session identity and supports resuming a saved OMP session. That is distinct from preserving an arbitrary shell process. [Session state](https://herdr.dev/docs/session-state/), [OMP integration](https://herdr.dev/docs/integrations/#omp)

Configuration is TOML. Built-in Catppuccin is `theme.name = "catppuccin"`. Runtime layout creation is driven through CLI/socket APIs; saved layout is server state. This first implementation ships the theme but does not pretend a static config already creates the complete three-pane workspace. The next spike must create the layout, repeat creation without duplication, detach, and restart. [Configuration](https://herdr.dev/docs/configuration/)

The plugin marketplace is an automatically discovered, unreviewed list. Plugins can execute host commands and are not sandboxed. A stable first-party project-tree solution was not established in this review. Recommended order for **this implementation**: ordinary Yazi pane, then a separately audited native tree if it proves useful. Yazi is a file manager rather than an IDE tree: file opening, mouse behavior, git decorations and following another pane's cwd require their own acceptance tests. [Marketplace](https://herdr.dev/docs/marketplace/), [plugins](https://herdr.dev/docs/plugins/)

## OMP: capabilities and integration boundaries

Canonical project: `can1357/oh-my-pi`. Native binaries avoid adding Bun merely to start the agent; Bun remains a supported upstream installation route. Global YAML is `~/.omp/agent/config.yml`, project config is `.omp`; discovery can also import other agents' rules, skills and MCP configuration. Precedence is subsystem-specific, so do not assume one universal merge order. [Configuration discovery](https://github.com/can1357/oh-my-pi/blob/main/docs/config-usage.md)

LSP and DAP tools exist, but actual language servers, adapter executables, debug configurations and project dependencies still need provisioning. Browser/search are built in; provider credentials and Chromium availability affect behavior. Subagents and extension hooks are built in. Extension code has host privileges. Validate the selected project's languages before claiming an IDE-equivalent setup. [LSP](https://github.com/can1357/oh-my-pi/blob/main/docs/lsp-config.md), [debugger](https://github.com/can1357/oh-my-pi/blob/main/docs/tools/debug.md), [extensions](https://github.com/can1357/oh-my-pi/blob/main/docs/extensions.md)

OMP supports MCP configuration and transport options, providing a plausible route to Mem0/Graphify, but their exact end-to-end integration has not been exercised here. Tool descriptions can consume context; actual startup and token overhead are unmeasured. Start with built-in functionality and zero additional MCP servers. [MCP](https://github.com/can1357/oh-my-pi/blob/main/docs/mcp-config.md)

## Memory and Graphify

OMP memory defaults to off. Built-in local summaries, Hindsight and Mnemopi deserve comparison before introducing Mem0. Local storage does not necessarily mean offline processing: the local summary pipeline calls configured models. Keep memory off until scope, provider data handling and costs are chosen. [Memory reference](https://github.com/can1357/oh-my-pi/blob/main/docs/memory.md)

Mem0 can be hosted or self-hosted, with model and storage dependencies. Retention, authentication and isolation depend on the deployment. No verified OMP-native Mem0 adapter was selected. Recommendation: optional later, not installed-but-unused. Disabling a client does not delete a hosted memory store. [Mem0 OSS](https://docs.mem0.ai/open-source/overview)

Graphify means `Graphify-Labs/graphify`, package `graphifyy`, not a similarly named graph server. Code AST parsing is local; optional semantic extraction of documents/media can use a model backend. Repository outputs live in `graphify-out/`. MCP serving is documented, but OMP-specific registration, large-repo cost, update accuracy, extras on Windows and failure behavior need a fixture and benchmark. Do not index repos or install git hooks automatically. [Graphify repository](https://github.com/Graphify-Labs/graphify), [quickstart](https://graphify.com/docs)

## Remote and YubiKey

Herdr uses system OpenSSH and includes the existing SSH config. Unix clients normally use a private per-attach control socket; Windows OpenSSH lacks that Herdr reuse path. Herdr can be told to use plain SSH with `remote.manage_ssh_config = false`. This repo does not write any SSH configuration. [Remote access](https://herdr.dev/docs/persistence-remote/)

An agent holding a key does not guarantee a FIDO2 signing operation can skip user presence. Test ordinary `ssh host`, touch/PIN, reconnect, and Herdr attach on the actual machine/key. Reuse can avoid a new authentication exchange; it does not alter key policy. No physical YubiKey test has been performed. Do not disable touch, host-key checks, or add agent forwarding. Unattended agents can remain in an already authenticated remote session; a new unattended login needs an explicitly approved separate identity or human authentication. Native Windows cannot currently be a Herdr remote target.

## Bootstrap conclusion

Use two small native launchers sharing one Python implementation and package manifest. The first milestone requires Python 3.9+, Homebrew for Unix package installation, or WinGet on Windows. The public commands run a preview by default. This deliberately **does not yet satisfy the clean-machine one-command acceptance criterion**: prerequisites, Linux GUI packaging, Windows Herdr/OMP installation, signed/pinned bundles and interactive acceptance remain work items.

Homebrew on Linux minimizes package-name drift for the CLI prototype but requires supported glibc/platforms and build prerequisites. It is not a promise of every Linux distribution or musl support. Compare mise-backed binary distribution before making this permanent. [Homebrew Linux](https://docs.brew.sh/Homebrew-on-Linux), [mise Aqua](https://mise.jdx.dev/dev-tools/backends/aqua.html)
