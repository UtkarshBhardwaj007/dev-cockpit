# Dev Cockpit agent instructions

Before editing, inspect the affected launcher, shared Python module, tests, and platform CI workflow. Keep changes cross-platform and avoid assuming that environment variables inherited after an installer describe the interactive user.

For Windows filesystem discovery, permission errors mean "not found". Do not scan protected service-profile or system paths without handling `OSError`; retain a user-home fallback. Add a regression test that injects the failing environment/path and proves the setup path continues.

Validate with `python -m unittest discover -s tests -v`, plus syntax/entrypoint checks appropriate to the changed launcher. Update README whenever the supported setup behavior or recovery guidance changes.
