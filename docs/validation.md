# Validation and next milestones

This is a bootstrap prototype, not the completed environment described in the original plan.

## Automated scope

- Python installer tests: preview is read-only, platform selection, profile validation, preservation of existing/edited config, symlink rejection, idempotent apply, ownership-aware uninstall, failed command handling.
- Native GitHub Actions runners: macOS, Ubuntu, Windows; Python tests, local entrypoint preview, and an install smoke test of the published one-liner after a main-branch push.
- Theme TOML is parsed, and vendored files are tied to upstream revisions/licenses.

The CI preview does not install the entire package stack. Config integration uses temporary homes. Green CI is not evidence that a GUI, hardware key or authenticated agent works.

## Next acceptance work

1. Provision prerequisites from a fresh OS, with explicit supported distro/architecture versions.
2. Pin installer bundles and tool versions, and verify downloaded release checksums/signatures.
3. Validate the implemented Linux Ghostty and native Windows Herdr/OMP installer adapters on real machines.
4. Exercise real package installation on disposable machines, twice, including failure/retry and PATH refresh.
5. Create Yazi + OMP + shell Herdr layout; verify startup, cwd, resize, focus, file opening, detach and reboot restore.
6. Validate Ghostty/WezTerm fonts, key sequences, truecolor, clipboard and images on all three desktops.
7. On macOS, run the default setup, grant Hammerspoon Accessibility, quit and reopen Hammerspoon (macOS caches the grant for an already-running process), reload Herdr's config (`herdr server reload-config`), and confirm pinch-out/pinch-in zoom the focused Herdr pane in both Ghostty and WezTerm, including a named `dev-cockpit` session. Press `ctrl+alt+cmd+z` and confirm the alert reports "tap running, Accessibility granted, frontmost: Ghostty". Linux and Windows intentionally have no gesture bridge.
8. Validate project-specific LSP/DAP and agent authentication.
9. Test SSH with the owner's actual YubiKey policy; Windows remote-client limitations remain explicit.
10. Benchmark optional memory/Graphify only after the core experience is usable.

See the Actions page for actual run results; this file intentionally does not assert future CI outcomes.
