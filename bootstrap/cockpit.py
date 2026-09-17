#!/usr/bin/env python3
"""Public bootstrap entrypoint (shim).

Delegates all behavior to the unified CLI in dev_cockpit.cli so the setup
launchers (bootstrap/setup.sh and bootstrap/setup.ps1) and the shell functions
share a single implementation. Kept as a real file because the deployed runtime
and launchers reference bootstrap/cockpit.py explicitly.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None):
    from dev_cockpit.cli import main as cli_main
    return cli_main(argv)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)
