# Validation and next milestones

This is a bootstrap prototype, not the completed environment described in the original plan.

## Automated scope

- Python installer tests: preview is read-only, platform selection, profile validation, preservation of existing/edited config, symlink rejection, idempotent apply, ownership-aware uninstall, failed command handling.
- Editor tests (`tests/test_editor.py`): settings validation and argv handling, literal-path normalization, exact-location validation, session identity per worktree, capability gating for the code layout, missing-binary fallback to `$VISUAL`/`$EDITOR`, and read-only language/tool status that treats a permission error as "not found".
- Editor config tests (`tests/test_configuration.py`): the `dev-edit` bridge is installed on Unix only and is executable; its rendered content embeds the selected Python and deployed runtime; Fresh preferences and `editor.json` are macOS-only and create-only across `--force-config`; Windows receives neither.
- Native GitHub Actions runners: macOS, Ubuntu, Windows; Python tests, local entrypoint preview, and an install smoke test of the published one-liner after a main-branch push.
- Theme TOML is parsed, and vendored files are tied to upstream revisions/licenses.

The CI preview does not install the entire package stack. Config integration uses temporary homes. Green CI is not evidence that a GUI, hardware key or authenticated agent works.

## Next acceptance work

1. Provision prerequisites from a fresh OS, with explicit supported distro/architecture versions.
2. Pin installer bundles and tool versions, and verify downloaded release checksums/signatures.
3. Validate the implemented Linux Ghostty and native Windows Herdr/OMP installer adapters on real machines.
4. Exercise real package installation on disposable machines, twice, including failure/retry and PATH refresh.
5. Create Yazi + OMP + shell Herdr layout; verify startup, cwd, resize, focus, file opening, detach and reboot restore.
6. Complete the Phase 0 experiments that remain open in [editor-compatibility](editor-compatibility.md) — the record now covers Fresh 0.5.1 on macOS arm64 (open/save, exact locations, literal and colon filenames, config schema and location, cold-open timings). Still unverified: two opens into one named session, Yazi opener focus, bulk-rename wait semantics, keyboard/mouse/clipboard/resize/zoom through Ghostty, dirty-buffer conflicts and crash recovery. Persistent routing is not implemented, so every open currently runs a foreground instance.
7. Build the code layout on a real desktop and confirm the pane ratios render as intended, the Editor/OMP/Shell context variables are present, and `dev files .` / `dev review .` create one tab each without duplicating on repeat. Confirm an existing classic workspace gains one Editor tab and that `dev open . --layout code` reports `CODE LAYOUT UNAVAILABLE` when Fresh is absent.
8. Provision the eight language packs and run the nine-language capability fixtures once runtimes are pinned. `dev editor languages install` intentionally refuses today, so this item cannot pass yet.
9. Validate Ghostty/WezTerm fonts, key sequences, truecolor, clipboard and images on all three desktops.
10. On macOS, run the default setup, grant Hammerspoon Accessibility, quit and reopen Hammerspoon (macOS caches the grant for an already-running process), reload Herdr's config (`herdr server reload-config`), and confirm pinch-out/pinch-in zoom the focused Herdr pane in both Ghostty and WezTerm, including a named `dev-cockpit` session. Press `ctrl+alt+cmd+z` and confirm the alert reports "tap running, Accessibility granted, frontmost: Ghostty". Linux and Windows intentionally have no gesture bridge.
11. Validate project-specific LSP/DAP and agent authentication.
12. Test SSH with the owner's actual YubiKey policy; Windows remote-client limitations remain explicit.
13. Benchmark optional memory/Graphify only after the core experience is usable.

See the Actions page for actual run results; this file intentionally does not assert future CI outcomes.
