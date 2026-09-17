# AI memory, code graphs, and language tooling

Dev Cockpit uses OMP's native local memory backend and the official
[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) package
`graphifyy[mcp]`. The installer supplies the tools; you choose which project to
enable. Setup does not index your home directory, open an AI conversation, or
create a cloud-memory account.

## Enable a project

These commands work in the configured shell on macOS, Linux, and native Windows.
Quote project paths containing spaces. Run from the project root, or replace `.`
with an explicit project directory:

```text
dev memory enable .
dev graph init .
dev graph doctor . --live
dev open .
```

`dev graph init` builds a local code graph, then merges one named stdio MCP server
into `.omp/mcp.json` and installs an OMP skill. In OMP, inspect `/mcp` and invoke
`/skill:dev-cockpit-graphify`, or ask it to query the graph for a symbol's callers.
Restart an already running OMP session after first enabling the integration.
Existing MCP allow/deny lists and disabled discovery providers remain in force;
if Graphify is absent in OMP, inspect those settings with `/mcp`.

`dev open` passes this project's memory overlay to OMP. A plain `omp` invocation
uses your usual OMP settings; to use the overlay directly, run:

```text
omp --config .dev-cockpit/intelligence/memory.yml
```

Neither integration edits your existing `.omp/config.yml`, model selection,
authentication, or unrelated agent configuration. Graph initialization never runs
the upstream broad `graphify install`/`uninstall` commands.

## Persistent memory

There are two complementary local stores:

- **Explicit project notes:** `dev memory remember . --text "The queue uses exponential backoff"`
  saves a deduplicated note immediately. `dev memory show .` reads it without a
  model or network. An OMP always-apply rule tells the agent to read relevant notes
  from `.dev-cockpit/intelligence/notes.json`, verify them against current code,
  and cite notes that influence a decision. Notes survive process restarts and
  disabling the integration. Edit this JSON file to correct or remove a note.
- **Native OMP summaries:** the project overlay selects `memory.backend: local`
  and enables `autolearn`. OMP extracts and consolidates prior persisted sessions
  and injects relevant project memory into later sessions. Its `learn` tool can
  capture a durable lesson. Use `/memory view`, `/memory stats`, and
  `/memory diagnose` inside OMP; `memory://root` and
  `memory://root/learned.md` expose native artifacts.

**Local storage does not mean offline inference.** Native summary extraction uses
OMP's configured `default` model and consolidation uses `smol` with fallbacks.
If these models use a hosted provider, the session material processed by memory
goes to that provider and may incur charges. Configure local models in OMP if you
need local inference; Dev Cockpit does not change your provider or reuse another
agent's tokens. See [OMP memory](https://github.com/can1357/oh-my-pi/blob/main/docs/memory.md)
and [local models](https://github.com/can1357/oh-my-pi/blob/main/docs/local-models.md).

The overlay limits extraction to eight sessions per startup, concurrency two,
and a 3,000-token injected summary. OMP normally waits until a session has been
idle for 12 hours before considering it. A fresh installation therefore need not
have a generated summary immediately. `/memory enqueue` schedules consolidation;
use `/memory diagnose` to distinguish no eligible sessions from provider errors.
`dev memory doctor .` checks local setup, not provider authentication or model
quality. Native memories stay in OMP's own agent data directory and project scope.

The initial plan proposed Mem0 as a candidate. The shipped path uses OMP's native
backend so persistent memory works without a Mem0 subscription, another MCP
service, or extra credentials. No Mem0 adapter is installed. Other native OMP
backends remain configurable through your own settings; disable the cockpit
overlay before selecting one.

Do not put credentials or private keys in notes. Manual notes are user-supplied
data, not a secret vault. The generated state directory has its own `.gitignore`
and files are created privately; keep native OMP auth/session directories out of
version control as usual.

## Graphify lifecycle

```text
dev graph install
dev graph init .
dev graph update .
dev graph doctor . --live
dev graph disable .
```

- `install` reuses a compatible existing CLI plus `graphify-mcp`. Otherwise it
  uses `uv` to install the pinned `graphifyy[mcp]==0.9.57` under
  `~/.local/share/dev-cockpit/graphify/` with Python 3.12. This avoids changing a
  project's Python environment. `dev graph install --upgrade` explicitly
  reinstalls the repository's pinned version and dependencies; normal setup never
  requests upgrades or reinstalls.
- `init` selects only the named project and uses
  `graphify extract --code-only --no-cluster`. It excludes cockpit/OMP generated
  directories and preserves Graphify's normal ignore behavior. This path parses
  source locally and never requests semantic extraction, embeddings, community
  labeling, or hosted memory. Unsupported code languages may produce fewer or no
  symbols; Markdown/PDF/media content is deliberately excluded.
- `update` checks a content fingerprint first. An unchanged project reuses its
  graph without running extraction. When files change, Graphify incrementally
  parses changed files and removes deleted code. `--force` requests a full
  reindex. A failed extraction restores the previous graph and keeps it marked
  stale. No automatic Git hooks or background watchers are installed.
- `doctor --live` checks freshness and project registration, then starts the real
  stdio MCP server, completes initialization, lists its tools, and calls
  `graph_stats`. It stops that diagnostic server afterwards. OMP starts its own
  server when the project session needs it.
- `disable` removes the unchanged owned skill and MCP entry. It retains the graph
  and any user-edited entry or file. If you edited the entry, remove or disable it
  yourself through OMP after reviewing it.

Graph artifacts are stored under
`.dev-cockpit/intelligence/graph/graphify-out/`. Query the same graph directly:

```text
graphify query "Which functions call twice?" --graph .dev-cockpit/intelligence/graph/graphify-out/graph.json
graphify export html --graph .dev-cockpit/intelligence/graph/graphify-out/graph.json
```

The export command creates `graph.html` beside the graph. Open it in your browser
for a visual map. The default code-only build skips community clustering, so the
graph emphasizes symbols and relationships. Graphify's optional semantic and
clustering workflows are separate upstream features; they can require additional
dependencies and a configured model provider. See the
[official CLI documentation](https://github.com/Graphify-Labs/graphify#cli-usage).

MCP registration uses absolute paths to the installed executable and project
graph, so it also works when OMP is launched without your interactive shell PATH.
The generated `.omp/mcp.json` entry is machine-specific: run `dev graph init .`
after moving the project or provisioning a second machine. Review generated
`.omp/` files before committing; only the `.dev-cockpit/intelligence/` directory
is ignored automatically. OMP's authoritative schema and merge behavior are
documented in [MCP configuration](https://github.com/can1357/oh-my-pi/blob/main/docs/mcp-config.md).

## Disable memory without losing saved data

```text
dev memory disable .
dev memory doctor .
```

This removes unchanged cockpit configuration and stops passing the overlay.
It retains manual notes and OMP's native memory. Your existing user/project OMP
settings take effect again, including any memory backend you configured yourself.
Deleting native memory is a separate deliberate action: review `/memory clear`
inside OMP for the active backend and project before using it.

## Language intelligence and debugging

OMP already provides LSP and DAP tools. It discovers supported servers from
project markers and installed executables; it does not install every compiler
and debugger on your machine. Use the installed `mise` and `uv` to provision the
languages each project actually needs, preserving the project's existing lockfiles
and version pins.

| Project | Typical tools | Provisioning and launch |
| --- | --- | --- |
| Python | `basedpyright`, `debugpy` | Select Python with `mise use python@3.12` if the project has no version pin; in a uv project, `uv add --dev basedpyright debugpy`, then `uv run dev open .` so the project virtual environment is on PATH. |
| JavaScript/TypeScript | Node, TypeScript, `typescript-language-server` | Use the project's Node pin through `mise install`; add the language server using the project's package manager. OMP searches `node_modules/.bin`. TypeScript 7 has a separate native LSP path. |
| Go | Go, `gopls`, Delve (`dlv`) | Use the project's Go pin through mise; install pinned `golang.org/x/tools/gopls` and `github.com/go-delve/delve/cmd/dlv` releases with `go install`. Put the resulting Go bin directory on PATH. |
| Rust | Rust toolchain, `rust-analyzer`, `lldb-dap` or `codelldb` | Keep the project's rustup/mise toolchain choice; add `rust-analyzer` to that toolchain and install a debugger supported on your host. |
| Shell | `bash-language-server` | Install with the project's Node package manager or a pinned mise npm backend; OMP detects it for matching shell project markers. |

For nonstandard commands, extend `.omp/lsp.json` or `.omp/dap.json` explicitly.
The installer leaves existing language/debugger configuration intact. Launch OMP
from the project root so marker detection works. See
[LSP configuration](https://github.com/can1357/oh-my-pi/blob/main/docs/lsp-config.md)
and [debugger setup](https://github.com/can1357/oh-my-pi/blob/main/docs/tools/debug.md).
JavaScript debugging uses Microsoft's vscode-js-debug DAP server; the OMP adapter
name `js-debug-adapter` is **not** an npm package. Follow OMP's documented tarball,
Mason, or `JS_DEBUG_DAP_SERVER` setup for that adapter.

## Verification scope

The deterministic tests cover merge preservation, repeat-run no-ops, private
installation commands, config disable/restore behavior, note persistence and
project isolation, malformed state, symlink rejection, concurrent operations,
stale graphs, and rollback after failed extraction.

The opt-in live test installs no packages itself. Set `GRAPHIFY_TEST_BIN` to a
directory containing the pinned real `graphify` and `graphify-mcp`, then run:

```text
python -m unittest discover -s tests -p "test_intelligence*.py" -v
```

It extracts a synthetic Python repository, excludes a synthetic Markdown
document, queries `twice` through real MCP, verifies unchanged graph reuse,
incremental additions and deletions, and safe disable with the graph retained.
No personal repository, transcript, token, or hosted provider is used. Set
`OMP_TEST_BIN` to the pinned OMP executable to run the second live test: it checks
all five memory overlay values through native `omp config get` with isolated
child-process state and no credentials. Model-backed memory consolidation and
actual language debugger sessions require your selected provider and project
toolchains.
