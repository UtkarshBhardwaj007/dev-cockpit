#!/bin/sh
# Public launcher: preview by default. Python 3.9+ is required in this milestone.
set -eu
command -v python3 >/dev/null 2>&1 || { echo 'Python 3.9+ is required; install it and rerun. See README prerequisites.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo 'Python 3.9+ is required.' >&2; exit 1; }
# A checked-out copy works offline. Piped invocations fetch a repository archive.
case "$0" in
    */setup.sh)
        if [ -f "$(dirname "$0")/cockpit.py" ]; then
            exec python3 "$(dirname "$0")/cockpit.py" "$@"
        fi
        ;;
esac
command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo 'tar is required.' >&2; exit 1; }
ref=${DEV_COCKPIT_REF:-main}
case "$ref" in ''|*[!a-zA-Z0-9._-]*) echo 'Invalid DEV_COCKPIT_REF; use a tag or commit SHA.' >&2; exit 1;; esac
scratch=$(mktemp -d "${TMPDIR:-/tmp}/dev-cockpit.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT HUP INT TERM
curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 3 \
    "https://codeload.github.com/UtkarshBhardwaj007/dev-cockpit/tar.gz/$ref" -o "$scratch/repo.tar.gz"
mkdir "$scratch/repo"
tar -xzf "$scratch/repo.tar.gz" --strip-components=1 -C "$scratch/repo"
python3 "$scratch/repo/bootstrap/cockpit.py" "$@"
