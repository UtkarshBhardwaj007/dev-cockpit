# Editor cheat sheet

Fresh is the managed editor on macOS. Its integration is **experimental** on Linux
and Windows, so those platforms keep the classic layout and their existing
editor. Qualification status and open questions live in
[editor-compatibility](editor-compatibility.md).

## Open files

| Command | What it does |
|---|---|
| `dev open .` | Create or reuse the project workspace (classic layout) |
| `dev open . --layout code` | Editor-centric layout: Editor, OMP, Shell (macOS with Fresh installed) |
| `dev edit -- src/app.py` | Open a file with the configured editor backend |
| `dev edit --line 42 --column 5 -- src/app.py` | Open an exact location (requires Fresh) |
| `dev edit --standalone --wait -- notes.txt` | Run a foreground editor and wait for it to finish |
| `dev edit -- .` | Open a directory as the editor project |
| `dev files .` | Create or focus the project's Yazi tab |
| `dev review .` | Create or focus the project's LazyGit tab |
| `fe` | Fuzzy-pick a file from anywhere and open the pick |
| `fv` | Fuzzy-pick a file and page it with `bat` |

A directory may be opened only as the sole path. Mixing a directory with file
paths, an unreadable file, or a new file whose parent does not exist is refused
with an explanation rather than being silently reinterpreted.

## Inside the editor

These are the intended interactions, chosen so that no modal editing knowledge is
required. Every action is also reachable from Fresh's command palette
(`Ctrl+P`, then `>` for commands), which is the reliable route. The chords below
are the documented targets, **not yet verified against a running Fresh release**:
a terminal can capture some combinations, so confirm the binding in the palette
before relying on a key.

| Action | Route |
|---|---|
| Open a file by name | `Ctrl+P` file finder |
| Run a command | `Ctrl+P`, then `>` |
| Save | `Ctrl+S` (save is explicit; autosave is off) |
| Close a buffer | palette: close tab (the workspace and other buffers stay open) |
| Undo / redo | `Ctrl+Z`, then the palette's redo action (the redo chord is not verified here) |
| Search in file | `Ctrl+F` |
| Go to line | `Ctrl+G` |
| Jump to definition | palette: go to definition, or `F12`-style binding if the terminal delivers it |
| Find references / rename | palette: references, rename symbol |
| Diagnostics | palette: diagnostics / problems panel |
| Review changes | palette: review (unstaged, staged or branch comparison) |
| Return to files | `dev files .`, or focus the Files tab in Herdr |
| Return to review | `dev review .`, or focus the Review tab in Herdr |

Line numbers, syntax highlighting and current-line emphasis work offline without
any language server. Completion, navigation, rename and diagnostics additionally
need the matching language pack.

## Language packs

```sh
dev editor languages list          # read-only: configured packs and tool status
dev editor languages install go    # provision one pack
dev editor languages install all   # provision every pack
```

Pack IDs: `go`, `python`, `java`, `typescript`, `cpp`, `csharp`, `rust`, `bash`.
`javascript`, `js` and `ts` are accepted as aliases for `typescript`; `all`
installs the eight packs covering the nine languages. **Provisioning is not
implemented yet** — the command refuses and changes nothing until runtimes,
versions and package sources are pinned and tested. Missing tools never prevent
ordinary editing.

## Editor preferences

`~/.config/dev-cockpit/editor.json` (macOS/Linux) or
`%APPDATA%\dev-cockpit\editor.json` (Windows) selects the backend:

```json
{
  "schema": 1,
  "backend": "fresh",
  "external_command": null,
  "external_wait_command": null,
  "language_packs": []
}
```

For an external editor, command fields are JSON argv arrays, so flags and paths
with spaces stay intact:

```json
{
  "schema": 1,
  "backend": "external",
  "external_command": ["code", "--reuse-window"],
  "external_wait_command": ["code", "--reuse-window", "--wait"],
  "language_packs": []
}
```

`dev edit` and the managed Yazi opener use this backend. The separate
`external` Yazi opener always uses your existing `$VISUAL`/`$EDITOR`, and `bat`
stays available as a read-only viewer. `$EDITOR`/`$VISUAL` are treated as a
single executable, so `code --wait` belongs in the argv form above, not in the
environment variable.

## Health and recovery

```sh
dev editor doctor .        # binary, version, support status, routing, config path, fallback, languages
dev doctor                 # EDITOR line; missing Fresh is an error on macOS, informational elsewhere
```

`dev editor doctor` reports four things that are easy to confuse:

- `EDITOR READY|MISSING` — whether the selected backend's binary was found, plus
  its `--version` output.
- `SUPPORT QUALIFIED|EXPERIMENTAL` — whether this platform is a qualified Fresh
  target. macOS is qualified; Linux and Windows are experimental.
- `ROUTING FOREGROUND` — persistent routing into a running editor session is not
  implemented yet, so every open runs a foreground instance.
- `FALLBACK EXTERNAL|UNAVAILABLE` — when Fresh is absent, the configured
  `$VISUAL`/`$EDITOR` is used and named. With neither available the command
  refuses with the repair options instead of a bare launch failure.

Recovery:

- **Fresh missing or broken:** rerun setup (`dev`), which reinstalls the package
  on macOS. A user-managed Fresh on PATH is never replaced.
- **`dev edit` refuses an exact location:** the path contains `:` and Fresh's
  location syntax is ambiguous for it. Open the file without `--line`, or use a
  path without a colon.
- **`dev open . --layout code` reports `CODE LAYOUT UNAVAILABLE`:** the code
  layout needs a qualified platform *and* a Fresh binary. The command keeps the
  classic workspace instead of creating a broken pane; the message names which
  condition failed.
- **An editor pane died:** `dev open . --layout code` focuses the existing
  Editor pane or adds one tab to a classic workspace. It never rebuilds the live
  layout, so unsaved work elsewhere is preserved.
