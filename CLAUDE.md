# Dev Cockpit contributor notes

Run `python -m unittest discover -s tests -v` before handing off a change. Native Windows behavior must be covered with deterministic unit tests and exercised by the Windows CI jobs; do not treat a macOS/Linux simulation as proof of Windows installer behavior.

Windows package discovery is best-effort. Never let a missing or access-denied path in `LOCALAPPDATA`, `PATH`, a registry value, or a system font directory abort setup. Always retain a fallback derived from the selected user home, and keep package writes limited to that home or the package manager.

The public launchers run configuration before package installation. Preserve that ordering unless it is intentionally redesigned, and make every post-configuration package probe non-fatal when it only checks for existing software.
