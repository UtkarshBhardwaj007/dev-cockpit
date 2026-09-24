# Editor compatibility record (Phase 0)

Status: **qualified on macOS arm64 against Fresh 0.5.1**, with the gaps listed
below still open. Everything in "Observed" was measured on the machine described
below; anything unmeasured is labelled as such.

Qualification date: 2026-09-22.

## Environment under test

| Item | Value | How it was read |
|---|---|---|
| OS | macOS 26.6.2 (build 25G83) | `sw_vers` |
| Architecture | arm64 (Apple Silicon) | `uname -m` |
| Fresh | 0.5.1 (`/opt/homebrew/bin/fresh`, `fresh-editor` formula) | `fresh --version` |
| Fresh config schema | `version: 2` (also accepts `1`) | `fresh --cmd config show` |
| Python (managed runtime) | 3.14.7 (Homebrew `python@3.14`) | `python3 --version` |
| Herdr | 0.9.1 | `herdr --version` |
| Herdr socket protocol | `schema_version` 1, `protocol` 22, 103 request methods | `herdr api schema --json` |
| Yazi | 26.9.1 (Homebrew 2026-09-01) | `yazi --version` |
| LazyGit | 0.65.0 (Homebrew) | `lazygit --version` |
| bat | 0.26.1 | `bat --version` |
| Git | 2.50.1 (Apple Git-155) | `lazygit --version` |
| Terminal | not exercised (headless PTY harness) | — |

Intel macOS, Linux and native Windows were not tested. `manifests/downloads.json`
still pins Herdr **v0.9.0** while this machine runs **0.9.1**; the pinned release
has not been re-verified against the behavior below.

Fresh's own update channel reports `unknown`/`Unknown` for this Homebrew install,
so self-update provenance is not confirmed.

## Observed behavior

Measured with real PTY sessions (40x120) driven by the owned `~/.local/bin/dev-edit`
bridge and by direct `fresh` invocations.

### Paths, locations and quoting

| Case | Result |
|---|---|
| `dev edit -- <file>` through the bridge | Opens in Fresh; no fallback notice; exit code from the editor |
| `dev edit --line 4 --column 3 -- <file>` | Fresh lands on `Ln 4, Col 3` |
| Filenames with spaces, quotes, newlines | Passed as one argv element; opened literally |
| Literal file named `weird:name.py` (no location) | Opens that exact file; `Opened weird...` |
| Literal file named `weird:name.py` **at a location** (`weird:name.py:3`) | **Fresh opens an empty buffer named `weird:name.py:3`** — the real file is not read |
| `src:file.py` exists; asked for `src:file.py:3` | Same failure: empty buffer, real content not shown |
| `a` exists; asked for `a:4` | Opens `a` at `Ln 4` (no literal `a:4` present) |

Fresh therefore resolves `path:line:col` by probing the literal path first. When a
colon-containing file actually exists, the location suffix is **not** stripped and
the user gets an empty buffer. Our code refuses exact locations for colon paths
(`RoutingUnavailable`, message "ambiguous") rather than silently opening the wrong
thing — that refusal is now empirically justified, not just defensive.

Location syntax forms confirmed: `file:line`, `file:line:col`, and `file:line-end`
(which jumped to the end line, not a range selection).

### Editing basics

| Check | Result |
|---|---|
| Open, type, `Ctrl+S`, save | File on disk updated (`XYZalpha`) — explicit save works |
| Line numbers, status bar, menu bar | Present by default |
| Offline operation | Works; LSP is optional and absent tools do not block editing |

### Configuration

| Check | Result |
|---|---|
| Config location on macOS | `~/.config/fresh/config.json`; `fresh --cmd config paths` confirms |
| `XDG_CONFIG_HOME` respected on macOS? | **No** — config stayed at `~/.config/fresh` with XDG set |
| `~/Library/Application Support/fresh/config.json` | Not read for config (data dir only) |
| `HOME` override | Respected (used by the tests above) |
| `--config <path>` | Respected; loads the given file exactly |
| Declared `version: 1` vs `2` | Both load; reported as declared. A `1` file is **not** rewritten on disk |
| Managed config across a real UI run | Byte-identical afterwards — Fresh does not rewrite our file |
| Unknown keys | Silently ignored, no warning surfaced |

**Fixed as a result of this qualification:** `config_targets()` previously mapped
Fresh's config under `$XDG_CONFIG_HOME` like every other managed target. Fresh
ignores XDG on macOS, so that file was written where Fresh would never read it.
The mapping now always uses `~/.config/fresh/config.json` on macOS, and
`config/fresh/config.json` declares `"version": 2` to match the shipped schema
(the earlier `1` was accepted but is not the current contract).

### Timings (PTY measurement, excludes package installs)

| Operation | Result |
|---|---|
| Cold open → first byte | min 10 ms, median 12 ms, p95 13 ms, max 14 ms |
| Cold open → file content visible (small file) | min 39 ms, median 40 ms, max 49 ms |
| Cold open → content visible, 0.74 MiB source | min 817 ms, median 830 ms, max 842 ms |
| Bridge (`dev-edit` → `dev edit`) → Fresh UI | reached Fresh UI, no fallback notice |

The plan's budget is "p95 under 500 ms to a usable editor frame" for a source file
under 1 MiB. Small files pass comfortably. The **0.74 MiB sample took ~830 ms and
missed that target**, so the budget is not met for larger files and should be
re-measured with a true 1 MiB fixture before it is quoted as passing.

## Known limits

- **Foreground only.** Persistent routing (`fresh -a NAME` plus an acknowledged
  open into a running session) is not implemented. `dev editor doctor` reports
  `ROUTING FOREGROUND`. A qualified probe of `fresh --cmd daemon open-file` with
  no daemon running **stayed alive and produced no output** for 3 s, confirming
  the plan's warning that it can block/attach rather than fail fast — so it is
  deliberately not used.
- **Exact locations on colon paths** fall back to refusal for the reason above.
- **No Windows bridge.** Only the POSIX `dev-edit` wrapper is generated; Windows
  keeps `code -w` and receives no editor defaults.
- **No language pack provisioning.** All eight packs are listed and inspected;
  `languages install` refuses until runtimes and versions are pinned.
- **No script/plugin automation.** `fresh --cmd script ...` and
  `fresh --cmd command ...` require being inside a Fresh session
  (`$FRESH_SESSION`) or an explicit `--session`; the API declaration files only
  appear after the editor has been started once. Not needed for v1.

## Still to verify (not covered here)

1. Two file opens into one named session; neither creates a second UI nor loses
   dirty text.
2. Yazi `Enter` opener focus behavior in a real Herdr session, and standalone
   Yazi launching an interactive editor.
3. Wait semantics for a Git-style temporary file and Yazi bulk rename.
4. Keyboard, mouse, clipboard, resize and zoom through Ghostty → Herdr → Fresh,
   including Herdr `mouse_capture` and `copy_on_select`.
5. Dirty-buffer versus external-write conflicts, and recovery after killing only
   the fixture editor.
6. Herdr v0.9.0 compatibility, or a justified manifest upgrade.
7. Language and review smoke tests for all eight packs, prioritizing Java, C# and
   C++ risk.

## Gate

Ordinary editing, exact locations on colon-free paths, save, configuration and
literal-path handling pass on macOS arm64. The colon-path location bug and the
large-file timing target are recorded above; neither blocks foreground editing,
and both are contained by explicit refusals or documented limits rather than
silent wrong behavior. Windows/Linux remain experimental and unqualified.
