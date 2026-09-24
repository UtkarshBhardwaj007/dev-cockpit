# Dev Cockpit: a fast, complete terminal editing experience

Research date: 2026-09-21. Status: **partially implemented** — see the overlay below. The body of this
document remains the research and design record; where it describes behavior, the overlay states what
actually landed.

## 0. Implementation status (2026-09-21)

Implemented and tested in this repository:

- **Phase 1 — foreground editing.** `dev_cockpit/editor.py` owns editor settings, literal-path
  normalization, exact-location validation, per-worktree session identity and argv construction.
  `dev edit` runs a foreground instance and returns its exit code; `--standalone` and `--wait` are
  honored. The generated `~/.local/bin/dev-edit` bridge routes Yazi and `fe` through the same module
  and passes each path as one literal argv element.
- **Capability gating.** `dev open . --layout code` refuses to build an editor pane unless the
  platform is qualified *and* Fresh is on PATH; it prints `CODE LAYOUT UNAVAILABLE` with the reason and
  keeps the classic workspace. The classic layout is the default and is never rebuilt underneath a
  running workspace; an existing classic workspace gains one Editor tab on first request.
- **`dev files`, `dev review`, `dev editor doctor`, `dev editor languages list`**, added to both shell
  dispatch allowlists, plus an `EDITOR` line in `dev-doctor` that is an error on macOS and
  informational elsewhere.
- **Create-only editor preferences** (`config/fresh/config.json`, `config/editor/editor.json`) that
  survive setup, `dev-update` and `--force-config`, matching the existing OMP exception.
- **Fallback, never silent.** With Fresh absent, `dev edit` and `fe` use `$VISUAL`/`$EDITOR` and say so;
  with neither available they refuse with the repair options.
- **Yazi openers** separated into managed `edit`, `bulk-rename` (blocking) and `external` entries.
- **Tests and docs.** 224 tests pass (5 skipped). README, `docs/editor.md`,
  `docs/editor-compatibility.md`, `docs/customization.md`, `docs/themes.md`, `docs/decisions.md`,
  `docs/validation.md` and CI were updated.

Qualified since the overlay above was written:

- **Phase 0 (partially).** Fresh 0.5.1 is installed on macOS arm64 and has been exercised through the
  owned bridge: foreground open/save, `--line`/`--column`, literal and colon-containing filenames,
  config schema/location behavior, and cold-open timings. That qualification found and fixed two real
  defects — Fresh's config was mapped under `$XDG_CONFIG_HOME` although Fresh 0.5.1 ignores XDG on
  macOS, and the managed config declared schema `version: 1` instead of `2`. It also produced evidence
  that Fresh opens an **empty buffer** for `path:line` when the literal colon-containing path exists,
  which justifies the existing refusal for exact locations on those paths.
  `docs/editor-compatibility.md` holds the measurements and the experiments still outstanding
  (named-session reuse, Yazi focus, bulk-rename wait, mouse/clipboard/zoom, conflict handling,
  language packs).

Deliberately **not** implemented, with the gate still closed:

- **Remaining Phase 0 items.** Yazi opener focus in a real Herdr session, two opens into one named
  session, bulk-rename wait semantics, Ghostty mouse/clipboard/resize/zoom, dirty-buffer conflict
  handling and crash recovery are all still unverified. The 0.74 MiB cold open (~830 ms) missed the
  plan's p95-under-500 ms target, recorded in the compatibility file rather than glossed over.
- **Persistent routing (Phase 2).** `editor doctor` reports `ROUTING FOREGROUND`; every open runs a
  foreground instance. No `fresh -a NAME` daemon routing, startup lock or acknowledged open yet.
- **Language packs (Phase 3).** `dev editor languages list` inspects all eight packs, but
  `dev editor languages install` refuses until runtimes, versions and package sources are pinned.
- **Windows bridge.** Only the POSIX wrapper exists; native Windows keeps `code -w` and receives no
  editor defaults.

Validation for this implementation: `python3 -m unittest discover -s tests -v` → 224 tests, OK
(5 skipped); `sh -n bootstrap/setup.sh`, `bash -n config/shell/init.sh`,
`sh bootstrap/setup.sh --dry-run` and `python3 bootstrap/cockpit.py --platform windows --dry-run` pass.

## 1. Decision

**Recommend Fresh as the default editor, integrated with the existing Herdr + Yazi + OMP + LazyGit stack.** Give editing a large, persistent pane. Keep Yazi for file operations and route its selections into that editor. Reuse LazyGit for Git operations; expose Fresh's review UI for reading changes and keeping local review notes.

The owner confirmed: **prefer an actual IDE-like experience; unfamiliar with Vim/Neovim**. Familiar shortcuts are preferred, although learning another editing model would be acceptable if the overall experience warranted it. Therefore choose familiar editing by default; do not make Vim knowledge a prerequisite.

Confirmed languages: **Go, Python, Java, JavaScript, TypeScript, C++, C#, Rust and Bash**. All nine are in scope for language intelligence on macOS; they are not a future wishlist. JavaScript and TypeScript share one installable pack, making eight packs total.

**macOS is mandatory. Windows and Linux are desirable, not release blockers for the new editor experience.** Prioritize macOS + Ghostty + Herdr, beginning with Apple Silicon and documenting Intel qualification separately. Preserve the repository's existing cross-platform setup and CI. Implement portable shared code, but label unqualified editor integrations experimental and retain the existing classic layout/openers on those platforms. Optional-platform editor failures must not force a different editor choice or delay a qualified macOS release.

Throughout this plan, Windows/Linux bridge details specify the intended portable design and their later qualification criteria. They do not require completing those adapters before the macOS release. Gate package entries, managed editor config/openers and the new default layout by qualified platform capability, so common config application never activates an unavailable editor. New commands on an unqualified platform should explain support status and offer the existing workflow rather than changing it silently.

Fresh best matches the requested interaction style on paper: ordinary editing, menus, mouse input, tabs, line numbers, multiple cursors, and language-server support. Its built-in review tools are especially relevant. This is a researched recommendation, **not a measured claim that Fresh is faster or more reliable than Neovim**. Fresh is evolving rapidly; Phase 0 must qualify an actual release before making it the default. [Fresh upstream](https://github.com/sinelaw/fresh), [editing](https://getfresh.dev/docs/features/editing), [Git review](https://getfresh.dev/docs/features/git)

### Alternatives considered

| Option | Strength for this request | Cost or limitation | Decision |
|---|---|---|---|
| Fresh | Familiar interaction, integrated IDE features, review UI; relatively little configuration | Younger integration surface; release/package drift and terminal behavior need qualification | Recommended default after Phase 0 |
| Neovim + a pinned LazyVim configuration | Extensive customization and established language/Git tooling | Modal workflow; plugins, parser tooling and compiler dependencies increase setup work | Best alternative if the owner prefers Vim or Fresh fails qualification |
| Helix | Integrated LSP, syntax parsing and multiple selections | Different modal editing model; upstream currently says a plugin system is not available | Good focused editor, weaker fit for the desired customizable review workflow |
| Micro | Familiar shortcuts, mouse, multiple cursors; simple installation | Advanced language/review behavior needs additional evaluation and plugins | Optional basic rescue editor; do not build the main IDE around it |
| VS Code via `code --wait` | Full graphical IDE and extensions | Opens a separate application; not an editor rendered inside a Herdr terminal pane | Preserve as an explicit external-editor option |

Sources: [LazyVim requirements](https://www.lazyvim.org/), [Helix](https://helix-editor.com/), [Micro](https://micro-editor.github.io/), [VS Code CLI](https://code.visualstudio.com/docs/configure/command-line). The recommendations and tradeoffs are this plan's assessment.

Do not implement all five. Implement one well. Do not fork Yazi into an editor, build a new text engine, embed Monaco in a terminal, replace Herdr, or add a second AI agent framework.

## 2. Repository facts and integration traps

Inspect these files again before editing; follow `AGENTS.md`.

| Existing location | Current behavior | Consequence |
|---|---|---|
| `manifests/tools.json` | Installs Yazi, bat, LazyGit, etc.; no guaranteed editor | Add a real editor package |
| `config/yazi/yazi.toml` | Unix opener uses `$EDITOR`, falling back to bat; Windows hardcodes `code -w` | Unix may only page a file; Windows assumes a separate GUI editor exists |
| `config/shell/init.sh`, `init.ps1` | Discover `nvim`, `vim`, `hx`, `nano`; preserve existing `EDITOR` | No managed editing experience; preserve user preferences when extending |
| Same shell files | `dev` forwards only an explicit subcommand allowlist | New commands must be added to both shell allowlists and Python dispatch, or they can accidentally invoke setup |
| Same shell files | `fe` treats the entire `EDITOR` value as one executable | Values such as `code --wait` do not work reliably; use a defined argv contract |
| `dev_cockpit/workspace.py` | `layout_tree()` allocates 72% of the top row to OMP and 28% to Files; Shell below | Simply replacing Yazi with an editor leaves too little room for code |
| `ensure_workspace()` | Reuses a canonical-project workspace and never rebuilds an existing layout | Preserve running agents and unsaved work during migration |
| `configuration.py` | Enumerated files, ownership ledger, backups, atomic writes; forced setup repairs owned edited files | Fresh's UI-written preferences need a create-only exception or a separate user layer |
| `configuration.py::_bases()` | Most Windows configs use Roaming; some apps use Local | Resolve editor config/data paths explicitly; do not assume all apps share a base |
| `packages.py` | `_accessible()` catches `OSError`; Windows discovery retains the selected-home fallback | Reuse this behavior for editor and language-tool discovery |
| `runtime.py` | Content-addressed runtime includes `bootstrap`, `dev_cockpit`, `config`, manifests and docs | Installed wrappers must use the deployed runtime, not a development checkout |
| `.github/workflows/ci.yml` | macOS, Linux, Windows; PowerShell 5.1 and 7 launcher checks | Extend this matrix; Linux-only tests are insufficient |

Local read-only checks found Herdr **0.9.1**, while `manifests/downloads.json` currently specifies **v0.9.0**. Do not assume an API found locally exists in the shipped version. `herdr api schema --json` on 0.9.1 exposes `pane.focus`, `tab.focus`, pane `env`, and argv `command` in `LayoutNode`. `herdr pane focus` CLI is directional; do not invent `herdr pane focus <id>`. Use the schema-verified socket request for direct focus.

The tracked `plan.md` was already deleted in the working tree before this research. This file is the newly requested plan, not a restoration of its earlier contents.

## 3. Target experience

### Daily flow

1. `dev open .` opens or reuses the project. The editor is immediately usable; OMP and a shell remain nearby.
2. `Ctrl+P` finds a file; `>` in the palette finds a command. Tabs retain open files. Line numbers and syntax colors are visible by default. [Palette behavior](https://getfresh.dev/docs/features/command-palette)
3. `dev files .` focuses a Yazi tab. Enter on a source file opens it in the existing editor and focuses the editor pane. Multi-selection opens several buffers without launching several editors.
4. `dev edit --line 42 --column 5 -- src/example.py` opens an exact location. `fe` uses the same route.
5. Completion, definition, references, rename, diagnostics and formatting are available for installed language packs. Missing language tools never prevent ordinary editing.
6. Review changes using Fresh's palette; use `dev review .` for the familiar LazyGit interface.
7. Repeat `dev open .`: retain the editor process, buffers, agent and shell. Detaching the cockpit leaves the session available; reboot recovery is a separate, explicitly tested feature.

### Default layout for new workspaces

Ratios refer to available content space after Herdr's own sidebar/borders:

```text
Herdr workspace: project
Tabs: [Code] [Files, created on demand] [Review, created on demand]

Code tab
+--------------------------------------+-------------------+
| Editor                               | OMP               |
| ~68% width; tabs, line numbers        | ~32% width        |
| palette, diagnostics on demand       |                   |
+--------------------------------------+-------------------+
| Shell / test output                                      |
| ~22% height                                             |
+---------------------------------------------------------+

Files tab: Yazi at full usable width; Enter returns to Code.
Review tab: LazyGit at full usable width.
```

Use a Herdr split tree: outer `down` ratio `0.78`; first child `right` ratio `0.68`, Editor then OMP; second child Shell. Confirm ratio semantics with the real pinned Herdr. Keep the editor's own file tree closed initially to avoid duplicated navigation.

For small terminals, document Herdr pane zoom (`prefix+z`) and keep all commands usable through text. Do not automatically rebuild a running layout on resize. A permanently visible Yazi sidebar can be a later wide-screen preset; do not squeeze four panes into the default.

### UX defaults

- Absolute line numbers, current-line highlight, indentation guides, matching brackets, dirty-tab marker, file encoding/line-ending status and readable diagnostics.
- Catppuccin Mocha with restrained accents, consistent with the rest of this repository. Use a verified built-in theme if available; otherwise supply a small licensed theme asset.
- No startup animation, forced welcome wizard, mandatory Nerd Font icons, or package downloads while opening a file.
- Save is explicit. Autosave and format-on-save start disabled. Offer per-language opt-in after formatting behavior is demonstrated.
- Keep ordinary click/selection, scroll, undo/redo, find/replace and multiple cursors available. Do not assume a terminal can deliver every GUI keyboard chord.
- `Ctrl+S`, `Ctrl+Z`, `Ctrl+P`, `Ctrl+F`, `Ctrl+G` are target shortcuts; verify actual defaults before documenting them. Prefer palette actions when a terminal captures a chord. Do not promise universal Cmd-key equivalents or Ctrl+Shift distinctions.
- Verify mouse events and clipboard through **Ghostty/WezTerm → Herdr → editor**, including Herdr's current `mouse_capture` and `copy_on_select`. Do not globally change terminal shortcuts to solve one editor conflict.
- Keep Fresh's own orchestration and embedded terminals out of the default cockpit UI. Herdr owns workspace layout and OMP remains the coding agent.

## 4. Architecture and command contracts

### One Python integration module

Create `dev_cockpit/editor.py`; keep shared behavior out of shell snippets. Suggested small internal boundaries:

```text
resolve_editor_settings(home, target, environment) -> validated settings
project_identity(project, herdr_session) -> stable key
build_editor_command(settings, files, location, mode) -> argv + child env
open_files(request) -> exit code
doctor_editor(...) -> structured checks
```

These are proposed repository interfaces, not claims about upstream APIs. Keep Python 3.9 compatibility and the standard-library-only runtime. Use lists for subprocess arguments and `shell=False`.

### Public commands

| Proposed command | Contract |
|---|---|
| `dev edit [--project DIR] [--line N] [--column N] [--standalone] [--wait] -- FILE...` | Open paths; location flags require exactly one file and positive integers |
| `dev files [PROJECT]` | Ensure/focus that project's Yazi tab; no duplicate tab on repeat |
| `dev review [PROJECT]` | Ensure/focus that project's LazyGit tab; no automatic checkout, stage, commit or push |
| `dev editor doctor [PROJECT]` | Report selected binary/version, config, session routing, language tools and recovery guidance |
| `dev editor languages list` | Show installed/configured language packs |
| `dev editor languages install PACK...` | Explicitly provision selected packs; IDs: `go`, `python`, `java`, `typescript`, `cpp`, `csharp`, `rust`, `bash`; `all` installs all eight |
| `dev open [PROJECT] --layout code\|classic` | `code` for new editor workspaces; `classic` preserves the current layout choice |

`dev edit` outside a cockpit runs a foreground editor and returns its exit code. It must not start Herdr merely to edit one file. Inside a managed workspace it normally routes to the persistent editor; `--standalone` always runs a foreground instance. `--wait` completes when editing is finished, not merely when the file-open request is acknowledged. Until remote waiting is qualified, implement waiting with the foreground path.

No files: open the project editor/empty editor. Directory argument: use it as the editor project only when it is the sole argument; do not read a directory as text. Refuse a mixture of directories and file paths with a useful explanation. New file paths are allowed when the parent exists and is accessible.

### Editor preferences and external editors

Add a small user-owned `editor.json` in the existing dev-cockpit config directory. Proposed schema:

```json
{
  "schema": 1,
  "backend": "fresh",
  "external_command": null,
  "external_wait_command": null,
  "language_packs": []
}
```

Supported v1 backends: `fresh` and `external`. For an external editor, command fields are **JSON argv arrays**, for example `["code", "--reuse-window"]` and `["code", "--reuse-window", "--wait"]`. Validate nonempty string elements. A GUI external backend opens files externally and is not treated as a persistent terminal editor pane. Do not advertise a managed Neovim backend until it exists.

The explicit cockpit backend controls `dev edit` and the managed Yazi default opener. Keep an additional “External editor” opener for existing `EDITOR`/`VISUAL` preferences. Preserve nonempty `EDITOR`, `VISUAL`, `GIT_EDITOR` and user-defined shell commands. When unset, setting `EDITOR=fresh` is sufficient for foreground third-party editing after Fresh is installed; do not set it to a shell function. For custom commands with flags, document the argv configuration instead of introducing `eval`. Bare editor executable paths containing spaces must work.

### Executable bridge for Yazi

Yazi launches commands in subprocesses; the interactive `dev` function is not a portable executable. Supply owned `dev-edit` and `dev-edit.cmd` wrappers in the selected user's `~/.local/bin`, and track them with the existing conservative ownership model. Generate their contents using the deployed runtime path and selected Python executable. Test quoting in bash/zsh, cmd.exe, PowerShell 5.1 and PowerShell 7. A `.ps1` file alone is insufficient for a Windows Yazi opener.

Use Yazi's documented `%s` path expansion for its current version; it already appears in this repository. Managed opener intent: `dev-edit -- %s`, with `block = true` so a standalone foreground fallback has a terminal. A live-session open should return quickly and switch Herdr focus. This combination must be exercised in a real Yazi session; unit tests of a TOML string do not prove it works. Keep bat as an explicitly named read-only viewer. Preserve media/archive handling and `q`/`Q` behavior. [Yazi opener semantics](https://yazi-rs.github.io/docs/configuration/yazi/)

The wrapper must not blindly re-emit untrusted arguments into a shell command. cmd.exe has special quoting/expansion rules even when Python itself uses argv. Include `%`, `!`, `&`, parentheses and quotes in Windows tests. If the wrapper cannot pass legal Windows filenames losslessly, use a small Yazi Lua bridge with structured process arguments; make that a tested exception, not a silent filename restriction.

Configure Yazi **bulk rename separately** to use `dev-edit --standalone --wait -- %s`; a nonblocking ordinary opener would let Yazi consume the rename file before editing finishes. Apply the same foreground contract to commit/rebase messages when explicitly configured by the user. Disable session restoration/hot-exit shortcuts for these temporary editing transactions using verified upstream controls: success must reflect a completed disk edit, not unsaved recovery state. Do not change global Git editor settings automatically. [Yazi bulk-rename configuration](https://yazi-rs.github.io/docs/tips/)

### Persistent editor routing

Use one editor per `(Herdr session, canonical project path)`. Include worktree paths in the identity; do not collapse sibling worktrees to their common Git directory. Do not key on directory basename or whichever directory Yazi currently displays.

Pass a small explicit context to managed panes: `DEV_COCKPIT_PROJECT`, `DEV_COCKPIT_HERDR_SESSION`, `DEV_COCKPIT_EDITOR_KEY`. Use Herdr layout-node environment fields after checking the shipped schema. Existing servers may have old environments: launching panes must not depend on the server inheriting new shell variables.

Fresh documents named daemons, non-attaching file opens, and a waiting variant. Candidate commands to qualify are `fresh -a NAME` and `fresh --cmd daemon open-file NAME FILE...`. A missing daemon can cause the latter to attach interactively, so it must never be assumed to be an always-noninteractive RPC. Bare `fresh` also has different orchestration behavior; use an explicit mode. [Fresh daemon documentation](https://getfresh.dev/docs/features/session-persistence)

Implement this state machine:

```text
request
  → resolve explicit project/context, canonicalize paths
  → foreground mode or external backend? launch and return
  → inspect exact workspace + managed editor pane + live editor session
  → healthy: deliver file request, await acknowledgement, focus Code + Editor
  → absent: create only the missing editor surface, wait for readiness, retry once
  → uncertain result: preserve processes/buffers; bounded error with recovery command
```

Use an atomic per-project startup lock with a bounded wait to prevent duplicate instances from simultaneous opens. Keep optional routing metadata beneath dev-cockpit's user state directory, never inside the repository. Treat metadata as a cache: validate live pane/session identity on every connection, write it only after readiness, and do not trust a stale PID. Do not persist credentials or Fresh scripting tokens there.

Use Herdr's existing `Herdr.request()` for API calls, including schema-verified `pane.focus` and `tab.focus`. Never type an `:edit` command or a filename into an arbitrary terminal pane. Focus errors should report that the file opened but focus failed; do not resend blindly and duplicate buffers.

Fresh's CLI supports location syntax that may overlap with legal filename characters. Our API keeps file, line and column separate. Qualification must cover drive letters and Unix names containing `:`, `@` and quotes. Use an upstream literal-path/structured method if available. If no lossless live route exists, use a verified literal foreground route and clearly report the degraded mode; never open a different path.

Fresh's scripting API is capability-scoped to terminals it launches. **Do not assume a sibling OMP/Yazi pane launched by Herdr can invoke `fresh --cmd script run`.** Use documented daemon file-opening for v1, and keep arbitrary scripting out of the bridge. [Fresh scripting scope](https://getfresh.dev/docs/features/scripting)

### Lifecycle and migration

- New workspace: create Code with editor, OMP and shell. Create Files/Review only when requested.
- Existing classic workspace: keep all current panes. On the first explicit editor request, add an Editor tab and focus it; record the association. Never apply a replacement layout over the live classic tab.
- Repeated requests: focus/reuse, retaining dirty buffers and terminal IDs.
- Editor closed normally: next request creates only an editor surface, not another OMP process.
- Editor crash: preserve recovery data; show a targeted restart route. Never run a global daemon kill or clear all sockets.
- Detach/reconnect: verify current session survives. Reboot: restore saved session metadata only after testing upstream behavior; do not claim a running daemon survives reboot.
- `dev-uninstall`: remove only unchanged owned files; retain personal editor settings, recovery data, review notes, packages and live sessions.

## 5. Language intelligence

Syntax highlighting and line numbers must work offline without any language server. Completion/navigation quality depends on installing and configuring the language's server. Fresh documents LSP configuration and missing-server status, including Python and JS/TS options. [LSP documentation](https://getfresh.dev/docs/features/lsp)

Ship eight explicitly installable packs covering the nine requested languages. These are proposed cockpit integrations to qualify, not a claim that installing Fresh installs these tools or delivers every IDE feature automatically:

| Pack | Proposed tools | Provisioning and acceptance |
|---|---|---|
| Go (`go`) | `gopls`; Go formatting through the server/toolchain | Pin server and compatible Go toolchain; isolate managed `GOBIN`. Test `go.mod`, `go.work`, cross-package imports, references and rename. [Go documentation](https://go.dev/gopls/) |
| Python (`python`) | `python-lsp-server` initially; optional separate Ruff formatter later | Isolated `uv` environment under cockpit data; no global pip modifications. Completion, definition, references, rename and diagnostics must resolve a fixture's local virtualenv dependency. Select/test an explicit formatter instead of assuming pylsp includes one. [Fresh Python setup](https://getfresh.dev/docs/features/lsp) |
| Java (`java`) | Eclipse JDT LS (`jdtls`); server formatting | Pin a compatible server JDK separately from the project's target JDK. Give each canonical project/worktree its own writable JDT LS workspace data. Test Maven and Gradle import, external dependency navigation, cross-file rename and diagnostics. [Eclipse JDT LS](https://projects.eclipse.org/projects/eclipse.jdt.ls) |
| JavaScript + TypeScript (`typescript`) | TypeScript + `typescript-language-server`; repository's formatter when configured | Prefer project-pinned tools; otherwise use an isolated managed npm prefix and supported Node runtime. Test `.js`, `.jsx`, `.ts`, `.tsx`, `jsconfig.json`/`tsconfig.json`, workspace imports and rename. [Server upstream](https://github.com/typescript-language-server/typescript-language-server) |
| C++ (`cpp`) | `clangd` + `clang-format` | Pin LLVM tools; locate a valid `compile_commands.json` or explain how to generate it. Test CMake fixture headers, include paths, compiler flags, definition/references and rename; diagnose absent build metadata. [clangd setup](https://clangd.llvm.org/installation) |
| C# (`csharp`) | `csharp-ls` (Roslyn-based), LSP formatting | Install a pinned .NET tool into a cockpit-owned tool path with its required SDK; respect project `global.json`. Test `.sln`/`.csproj`, package restore, completion, references, rename and diagnostics. [csharp-ls upstream](https://github.com/razzmatazz/csharp-language-server) |
| Rust (`rust`) | `rust-analyzer` + `rustfmt` | Respect `rust-toolchain.toml`; qualify rustup components/server versions and discover binaries without replacing the project's toolchain. Test Cargo workspaces, macros, cross-crate navigation and diagnostics. [rust-analyzer installation](https://rust-analyzer.github.io/book/installation.html) |
| Bash (`bash`) | `bash-language-server`, ShellCheck, shfmt | Pin Node/server and lint/format tools. Detect `.sh` files and Bash shebangs; test sourced functions, diagnostics and formatting. Keep POSIX sh and zsh detection distinct; document semantic limits for dynamic sourcing/rename. [Bash server upstream](https://github.com/bash-lsp/bash-language-server) |

Installation UX: `dev editor languages install all` provisions this owner's complete stack explicitly; individual packs remain available. `javascript` may be accepted as an alias for `typescript`, never as a duplicate install. Before changes, display missing runtimes, selected versions and package sources. Normal cockpit setup installs the editor, not every SDK. Opening a file starts only an already-installed relevant server; it never downloads a JDK, .NET SDK or compiler in the background.

Qualify **Java, C# and C++ early in Phase 0**, alongside a small Go/Python/TS/Rust/Bash smoke matrix. These integration choices deserve the most scrutiny before committing to Fresh: project import, workspace configuration and custom server requests can exceed generic LSP support. In particular, csharp-ls currently documents a .NET 10+ host requirement; record the pinned release's actual requirement rather than assuming the project SDK is enough. Do not depend on proprietary VS Code extension components for the C# pack. [csharp-ls requirements](https://github.com/razzmatazz/csharp-language-server)

For each pack, record the tested capability matrix: completion, hover, definition, references, rename, diagnostics, formatting and code actions. Test through Fresh, not only a standalone server. Missing standard navigation in an ordinary Java/C#/C++ project is a release issue, not something to dismiss as “LSP supported.” Document language-specific limits such as Bash's dynamic semantics and unqualified Razor/XAML/framework tooling. Full IntelliJ/Visual Studio feature parity and debugging remain outside v1.

Resolve/pin tested tool versions during implementation and record them in a language manifest; do not use `latest` in a reproducibility claim. Reuse mise where appropriate for runtimes, but do not silently modify a repository's mise/npm configuration. On Windows, verify `.cmd` entrypoints and server startup through the actual editor.

Use absolute server paths when practical. Respect project environments and root markers, including monorepos; do not start one server per buffer. Start servers lazily, show indexing/status, and keep editing responsive if they crash. Keep language-install operations separate from `dev edit` and shell startup. Measure cold indexing separately from interactive edit latency, especially Java/C#/C++; do not apply the editor-only memory budget to their language-server processes.

For an untrusted repository, retain the editor's trust handling and do not auto-approve project scripts or tasks. [Workspace trust](https://getfresh.dev/docs/features/workspace-trust)

## 6. Review and agent collaboration

### Required initial review experience

Expose Fresh's review commands through its palette and document a short workflow. Upstream describes working-tree/range/stash review, change navigation and persistent local comments with export. Keep these distinct from hosted GitHub reviews. LazyGit remains the existing place for staging, commits and branch operations. [Fresh review capabilities](https://getfresh.dev/docs/features/git)

Acceptance requirements we impose:

- Show the chosen comparison clearly: unstaged vs index, staged vs HEAD, or branch vs merge base. Do not label `main..HEAD` as merge-base review. Determine the actual default branch, allow explicit base selection, and handle repositories without `origin` or even an initial commit.
- Include untracked files explicitly; `git diff` alone omits them. Represent renames, deleted files, binary files, CRLF and submodule changes accurately or mark unsupported cases.
- Opening review must not change the Git index or working tree. Stage/discard controls act only on explicit interaction. Test the built-in discard behavior; disable or avoid binding it if it lacks a satisfactory confirmation/recovery story.
- `dev review` opens LazyGit; it must not scrape keyboard shortcuts to automate Fresh's review UI. Use the editor's palette until a supported command API is qualified.
- Keep review notes local. Markdown export is useful for handing a human's observations to OMP or a PR reviewer; publishing comments is a separate user action.

### Critical simultaneous-edit behavior

OMP can change a file while it is open. Test all three cases:

1. Clean editor buffer + external write: refresh safely and retain a sensible cursor position.
2. Dirty editor buffer + external write: show a conflict and offer compare/reload/keep-local/save-as; never silently replace either version.
3. File deleted/renamed or Git branch changed externally: show a clear state and preserve recoverable unsaved content.

Do not enable automatic format-on-save or autosave until this is reliable. Do not automatically insert text into an OMP prompt: an agent may already be running and terminal input may have different meaning.

### High-value follow-ups, after the core passes

| Feature | Concrete interaction | Scope boundary |
|---|---|---|
| Copy context for OMP | Copy project-relative `path:line-range`, selection and a short question to clipboard | User chooses what to send; no automatic upload or prompt submission |
| Review tour | Walk through changed files/findings with persistent local notes | Use verified APIs; no assumption that Herdr panes inherit Fresh scripting capabilities |
| Test failure navigation | Parse a supported test format; choose a failure to call `dev edit --line ...` | Start with Python unittest/pytest and TypeScript test output; never execute arbitrary log text |
| Workspace resume | Restore tabs, positions and splits with recoverable dirty buffers | Do not reopen tasks or rerun commands implicitly |
| Worktree-aware review | Separate editor/agent contexts per worktree | Reuse the canonical-path identity; no automatic branch checkout |
| Debugger | Breakpoints, step controls and variable inspection | Separate DAP qualification; not promised in v1 |

The most valuable polish is the browse → edit → inspect change → fix loop. Avoid spending the first release on animation, decorative dashboards, a second task orchestrator, or installing every language tool.

## 7. Implementation phases and acceptance gates

Implement in the following order. Each phase should be a reviewable change with tests and documentation. Future command names in this plan are contracts to implement, not commands that work today.

### Phase 0 — qualify upstream behavior before integration

Deliver `docs/editor-compatibility.md` with exact tested editor/Herdr/Yazi versions, package IDs, OS/architecture, command transcripts, known limits and timings.

Research snapshot: Fresh upstream's latest-release link resolved to **v0.5.1**, and Homebrew listed **0.5.1**. This is not a minimum-version guarantee and the website may describe newer behavior than a packaged build. Start qualification at that release; inspect its actual `--help`, bundled schema and changelog. [Release](https://github.com/sinelaw/fresh/releases/tag/v0.5.1), [Homebrew formula](https://formulae.brew.sh/formula/fresh-editor)

Candidate package mapping: Unix `brew` / `fresh-editor`, binary `fresh`; Windows WinGet `sinelaw.fresh-editor`, binary `fresh`. Fresh's own update-channel documentation identifies that WinGet ID; confirm it using `winget show --exact --id sinelaw.fresh-editor` on Windows before adding the manifest entry. [Upstream channel enum](https://docs.rs/fresh-update/latest/fresh_update/channel/enum.Channel.html)

Required experiments in a temporary fixture and isolated application state:

1. Ordinary open/edit/save/undo with line numbers, Unicode, CRLF and read-only files.
2. Two file opens into one named session; neither creates a second UI or loses dirty text.
3. Yazi opener returns and focuses the editor; standalone Yazi can still launch an interactive editor.
4. Wait semantics for a Git-style temporary file and Yazi bulk rename. Saving alone must not signal “done” if the editor still owns the operation.
5. Actual keyboard, mouse, clipboard, resize and zoom through Herdr on macOS; repeat on optional desktops when qualifying their support.
6. Dirty buffer vs agent/disk write conflict handling and recovery after a crash.
7. Herdr v0.9.0 compatibility, or a separately justified/tested manifest upgrade; do not rely solely on local 0.9.1.
8. Literal filenames on macOS; native Windows named-pipe/session routing as an optional-platform qualification item.
9. Language and review smoke tests; baseline timings from section 8. Exercise all eight packs, prioritizing Java/C#/C++ integration risk before building the full bridge.

Use disposable state roots/fixtures and the editor's verified isolation flags. Do not run prototype tests against the owner's live project editor or personal configuration.

**Gate:** if save/conflict safety, required language capabilities, or normal editing UX fails on macOS, do not promote Fresh. Record a reproducible failure and evaluate the Neovim alternative below against the owner's familiar-IDE preference; do not silently substitute a modal workflow. Windows/Linux failures are tracked separately and do not fail this gate. If only persistent routing fails, Phase 1 foreground editing can still ship as a clearly limited milestone; it is not completion of this plan. Do not write a replacement editor IPC server to conceal an upstream gap.

### Phase 1 — guaranteed editing from Yazi and the shell

Files: `manifests/tools.json`, `dev_cockpit/editor.py`, `cli.py`, `packages.py` as needed, `configuration.py`, wrapper templates under `config/`, both shell init files, Yazi config, tests and README.

1. Add qualified Fresh to `core` on macOS (no new profile necessary); enable the Linux/Windows manifest entries only when those integrations are qualified. Existing unsupported editor versions must produce a capability/version diagnostic; the package installer currently skips binaries found on PATH. Do not silently upgrade or replace a user-managed installation.
2. Implement foreground `dev edit`, exact-location handling, `--standalone`, `--wait`, argv settings and executable wrappers.
3. Add `edit`, `files`, `review`, `editor` to both shell dispatch allowlists as their commands land. Update tests that enumerate all CLI commands.
4. Route `fe` through shared editing logic. Use NUL-delimited Unix discovery/selection (`fd`/`fzf` capabilities checked), preserving legal newline-containing filenames; no shell evaluation of selections. Test PowerShell argument boundaries independently.
5. Route the macOS managed opener through the bridge; retain explicit external editor and bat choices. Replace the Windows `code -w` assumption when qualifying the Windows bridge, not with an uninstalled/untested command.
   Give bulk rename its own blocking opener and verify temporary-file completion/cancellation separately from ordinary file opening.
6. Introduce `config/fresh/config.json` with small tested defaults. Map config paths using the actual upstream rules: Unix XDG and Windows Roaming config are documented. Confirm data/recovery paths separately. [Configuration](https://getfresh.dev/docs/configuration/)
7. Treat Fresh preferences and cockpit `editor.json` as **create-only**, like OMP's exception: setup/update/`--force-config` must preserve subsequent UI edits. Ship future default migrations explicitly rather than silently resetting settings. Enumerate every owned theme/bridge target and keep uninstall behavior conservative.
8. Add editor health reporting to `dev-doctor` with a concise link to `dev editor doctor` for details. Missing editor is an error where the installed core profile promises it; unqualified optional platforms and uninstalled language packs are informational. A pack that was explicitly installed but is broken is an error with a repair command.

Gate: clean macOS setup can edit a file; repeated setup is safe; user preferences remain intact; existing cross-platform launcher and shell tests pass. README documents the macOS milestone and optional-platform status accurately. Do not regress existing Windows/Linux setup while adding the editor.

### Phase 2 — persistent editor and workspace integration

Files: `workspace.py`, `editor.py`, `cli.py`, Herdr/Yazi config, `tests/test_workspace.py`, new `tests/test_editor.py`, live integration tests.

1. Implement the Code layout and on-demand Files tab, with explicit per-pane context.
2. Implement named-session readiness, startup lock, acknowledged opens and safe focus.
3. Implement reuse/migration and `--layout classic` behavior without replacing running panes. The flag chooses creation behavior; it is not permission to destroy/rebuild an existing workspace.
4. Map multi-select and exact locations, including race/error paths described above.
5. Keep a blocked/foreground fallback for editors without live routing; report that mode honestly.

Gate: opening 20 files from Yazi yields one editor session, preserves unsaved text and OMP/shell terminal IDs, and routes two same-basename projects to different sessions. Legacy workspace gains one Editor tab once. An open command after a crash recovers or reports a bounded actionable error without hanging.

### Phase 3 — language packs, theme and interaction polish

Files: new language manifest/module if needed, Fresh config, doctor, `docs/editor.md`, tests.

Implement all eight language packs and status/recovery behavior from section 5. Suggested implementation batches: Go/Python/JS+TS/Bash, then Rust/C++, then Java/C#; the last batch is not deferred scope, and its feasibility was already checked in Phase 0. Match the theme. Write a short in-terminal-accessible cheat sheet covering open/save/close/undo/search/definition/diagnostics/review/return-to-files. Every advertised action must be available without learning modal commands.

Gate: fixtures for all nine requested languages pass their documented capability matrix on macOS; missing/offline tools preserve editing; macOS key and mouse checks pass. Report initial indexing and warm navigation performance separately for each pack. Windows/Linux pack qualification can follow without blocking release.

### Phase 4 — review and external-change safety

Files: `workspace.py`, `cli.py`, editor config, existing LazyGit config only if needed, review fixtures/tests/docs.

Implement `dev review`, document built-in review and notes, and qualify simultaneous editing. Test staged/unstaged/untracked/range review with a disposable Git repository. Add copy-context only if a supported editor command/plugin can provide an exact selection without reading unrelated files.

Gate: complete the acceptance journey in section 9. Local review notes survive restart and export correctly; merely reviewing leaves Git state unchanged.

### Phase 5 — release qualification

Update `.github/workflows/ci.yml`, `README.md`, `docs/customization.md`, `docs/themes.md`, `docs/decisions.md`, `docs/validation.md`, and the compatibility record. Keep platform limitations explicit. Do not claim CI proves clipboard/mouse UX or native Windows integration when those checks were skipped.

Only mark the required plan complete after Phases 0–5 pass on macOS for all requested languages and existing cross-platform setup remains intact. Full Windows/Linux editor qualification and the follow-up features are separate, nonblocking backlog items. Do not disable or make the repository's existing cross-platform regression jobs advisory to achieve this.

### Neovim alternative if selected

Keep the Python command/bridge/workspace boundaries. Use a dedicated `NVIM_APPNAME=dev-cockpit-nvim` so personal `~/.config/nvim` is untouched; honor Neovim's Windows LocalAppData conventions rather than the generic Roaming mapping. Start with a pinned LazyVim release/plugin lockfile and only the needed language/Git extras. Explicitly provision parser/compiler requirements; perform downloads during setup, never first edit. [Neovim config isolation](https://neovim.io/doc/user/starting/), [LazyVim requirements](https://www.lazyvim.org/)

Use `--listen` with a per-project local socket/named pipe and `--server ... --remote` for persistent opens. Neovim's built-in `--remote-wait` variants are documented as unsupported; use foreground instances for blocking workflows unless a separately tested wait bridge is added. Do not interpolate filenames into `--remote-send` keystrokes. [Neovim remote API](https://neovim.io/doc/user/remote/)

This alternative changes interaction to Vim-style editing and requires its own configuration/UX work. Do not present a handful of Ctrl-key remaps as full VS Code interaction parity or Fresh's Vim emulation as equivalent to Neovim's ecosystem.

## 8. Performance and reliability budget

These are proposed acceptance targets, not observed editor benchmarks. Record hardware, OS, editor build, terminal and Herdr version. Measure the entire bridge including Python/Herdr overhead; `fresh --version` timing is not startup UX.

| Operation | Initial target | Measurement |
|---|---|---|
| Cold file open, <1 MiB source, installed config | p95 under 500 ms to usable editor frame | 20 fresh process launches; exclude package installation; LSP readiness measured separately |
| Open another file in running editor | p95 under 150 ms to visible content/focus | 50 opens through the actual wrapper/Yazi route |
| Keystroke to visible update | p95 under 33 ms; no recurring >100 ms pauses | PTY/frame observation under typing, completion and agent output; confirm visually |
| Picker in 50,000-file fixture | first useful results under 300 ms | Type while discovery is still running; ignore dependency/build folders |
| Large-file mode, 20 MiB text / long single line | usable view under 1 s, no frozen input | Disable expensive semantic features when necessary; disclose degraded features |
| Idle editor, excluding LSP/OMP/Herdr | aim below 150 MiB and 1% of one CPU core | Measure process tree separately at idle for 60 s |

If a target is missed, record the measured result and cause before adding optimization. Large-file and missing-LSP behavior should degrade visibly. Do not load all repository files into memory, recursively scan protected directories, spawn repeated language servers, or poll Git on every keystroke. Debounce background work and cancel superseded searches. Install/update checks must not block editor startup; disable Fresh's automatic version-check telemetry in managed defaults using its documented setting. [Upstream update behavior](https://github.com/sinelaw/fresh)

## 9. Verification checklist

### Automated coverage

- `tests/test_editor.py`: command dispatch/argv, settings validation, missing binary/version, session identity, stale state, concurrent opens, readiness timeout, exit codes, external backend, literal paths and location parsing.
- `tests/test_configuration.py`: per-platform editor paths; preview has no writes; create-only UI preferences survive forced setup; idempotence, backups, symlink/junction handling and unchanged-owned uninstall. Deployed wrappers use the correct runtime/Python after update.
- `tests/test_packages.py`: package mapping and missing editor behavior; **inject a protected service-profile `LOCALAPPDATA` and `PermissionError`/`OSError`, prove the selected-user fallback is used and setup continues**. Extend to any new APPDATA/data-path probes; do not scan whole system/service profiles.
- `tests/test_shell.py`: all new `dev` commands forward rather than trigger install; existing user functions/aliases/env win; `fe` preserves selections and multi-word editor settings use argv.
- `tests/test_workspace.py`: new split structure, per-pane env, lazy tabs, repeat reuse, classic migration, no process termination after uncertain layout application, two worktrees, partial creation failures.
- `tests/test_launchers.py` and `tests/test_runtime.py`: public launchers remain thin, deployed assets include wrappers/theme/config, profile selection remains valid, no dev-checkout dependency.
- Disposable Git fixture: clean opening/review does not alter status/index; staged/unstaged/untracked/rename/delete/binary/range cases; notes export and UTF-8 paths.
- Language integration fixtures: all eight packs/nine languages, including Maven/Gradle import, .NET solution loading, C++ compile database, Go/Cargo workspaces, Python virtualenv, separate JS and TS projects, and Bash sourced functions. Assert actual language responses and edits; binary existence is insufficient.
- Real editor tests must use isolated config/data and actual binary versions. Recorder processes prove quoting only, not editor behavior. Make platform integration coverage visible rather than silently skipping all live tests.

Filename matrix: spaces, apostrophes, Unicode, leading dash, Unix newline, Unix `:`/`@`, Windows drive/UNC paths and legal `%`/`!`/`&`/parentheses. Do not generate filenames illegal on the OS under test. Keep paths separate from line/column metadata throughout.

### Required commands

```sh
python -m unittest discover -s tests -v
sh -n bootstrap/setup.sh
bash -n config/shell/init.sh
sh bootstrap/setup.sh --dry-run
python bootstrap/cockpit.py --platform windows --dry-run
```

Use `python3` where `python` is unavailable. In native Windows CI, retain both existing `powershell` and `pwsh` entrypoint checks; add real `.cmd`/Yazi invocation tests before claiming the Windows editor bridge works. Extend the existing isolated `--apply-config --home ...` checks to applicable editor assets, asserting unqualified platforms do not receive broken defaults. Keep optional editor qualification results separate from mandatory existing regression checks. Do not treat `--home` as a sandbox for package installation; the CLI explicitly rejects that combination.

Run live Herdr/editor tests only in a unique test session and temporary project, cleaning up only processes created by that test. Existing `COCKPIT_HERDR_TEST_BIN` support provides a starting pattern; update its three-pane expectations deliberately and add Files/Review assertions after their first use.

### Human desktop acceptance journey

Required on macOS + Ghostty, initially arm64 (record the actual macOS version and qualify Intel separately). Repeat on Linux x86_64 + Ghostty and native Windows x86_64 + WezTerm when promoting those optional integrations:

1. Install; repeat installation; open a project with a space/Unicode in its path.
2. Browse in Yazi, edit and save a source file, confirm line numbers/highlighting and inspect the disk result.
3. Open another file; switch tabs; undo; close one buffer without exiting the workspace.
4. Select/copy/paste with mouse and keyboard; test terminal resize and pane zoom.
5. Install all eight packs explicitly; exercise completion, jump-to-definition/back, references, rename, diagnostics and formatting in all nine language fixtures, with documented language-specific limits.
6. Have a fixture process edit a clean and a dirty open file; verify safe refresh/conflict behavior.
7. Review changes, add/export a local note, explicitly stage one hunk, and confirm only that intended index change occurred.
8. Detach/reattach; repeat `dev open`; verify dirty text, OMP and shell are preserved.
9. Terminate only the fixture editor to simulate a crash; demonstrate documented recovery.
10. Run offline, with a missing language server, with preserved personal editor config, and with an old classic cockpit workspace.

Record short captures/screenshots and actual timings. A qualified macOS release may ship while Windows/Linux editor checks remain pending; it must not claim those desktops were validated.

## 10. Definition of done and handoff

The required implementation is complete when a fresh macOS install can browse, edit, navigate code and review changes without leaving the terminal, with tested packs for Go, Python, Java, JavaScript, TypeScript, C++, C#, Rust and Bash, while preserving user settings and unsaved work. README explains the installed editor, layout, shortcuts, language installation, external-editor choice, limits and targeted recovery. Tests and the desktop acceptance record substantiate those claims. Existing Linux/Windows setup remains functional; full editor parity there is desirable but not mandatory.

Start with Phase 0, then implement Phase 1. Do not begin with a large plugin collection or AI features. If an upstream assumption fails, record the evidence and use the explicit fallback path; do not invent undocumented flags or silently reduce the promised behavior.

Research-turn validation: `python3 -m unittest discover -s tests -v` passed **162 tests, 5 skipped**; Unix launcher and shell syntax checks passed; Windows dry-run completed on macOS (preview only). Fresh was not installed or benchmarked, and no real desktop editor integration was tested during research. No application code or README behavior was changed by this planning task.
