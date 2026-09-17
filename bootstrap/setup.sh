#!/bin/sh
# Native Unix entrypoint. No flags means install the complete cockpit.
set -eu
mutate=1
has_action=0
force=0
for argument in "$@"; do
    case "$argument" in
        --dry-run|--doctor|--help|-h|--uninstall-config) mutate=0; has_action=1 ;;
        --install|--apply-config|--activate-shell) has_action=1 ;;
        --force-config) force=1 ;;
    esac
done
if [ "$has_action" -eq 0 ]; then set -- --install --apply-config "$@"; fi
# Repair project-created config by default so one command lands every update.
# Files the user created themselves are still never touched.
if [ "$mutate" -eq 1 ] && [ "$force" -eq 0 ]; then set -- "$@" --force-config; fi
# Refresh paths without modifying any shell/profile files.
PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"
export PATH
cache=${DEV_COCKPIT_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dev-cockpit}
sha_file() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    else sha256sum "$1" | awk '{print $1}'; fi
}
fetch() {
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 3 "$1" -o "$2"
}
sudo_run() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}
python_ready() {
    for python_candidate in python3 python3.12 python3.13 python3.14; do
        if command -v "$python_candidate" >/dev/null 2>&1 && "$python_candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
            python_command=$python_candidate
            return 0
        fi
    done
    return 1
}
if ! python_ready; then
    if [ "$mutate" -eq 0 ]; then
        echo 'PLAN: Python 3.9+ is required to run the detailed preview; installation would provision Python and the package manager.'
        exit 0
    fi
    case "$(uname -s)" in
        Darwin)
            if ! command -v brew >/dev/null 2>&1; then
                mkdir -p "$cache/downloads"
                brew_sha=12479a24be3f5307eecac7cde670fad7118640f031229e964f544b1367b52a41
                brew_script="$cache/downloads/$brew_sha"
                if [ ! -f "$brew_script" ] || [ "$(sha_file "$brew_script")" != "$brew_sha" ]; then
                    temporary=$(mktemp "$cache/downloads/.homebrew.XXXXXXXX")
                    fetch 'https://raw.githubusercontent.com/Homebrew/install/641127e1d6a9b5fd01dd4582abe174b7a4069bba/install.sh' "$temporary"
                    [ "$(sha_file "$temporary")" = "$brew_sha" ] || { rm -f "$temporary"; echo 'Homebrew installer checksum mismatch' >&2; exit 1; }
                    mv "$temporary" "$brew_script"
                fi
                sudo -v
                NONINTERACTIVE=1 /bin/bash "$brew_script"
            fi
            HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_UPGRADE=1 brew install python@3.12
            ;;
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                sudo_run apt-get update
                sudo_run apt-get install -y python3 curl ca-certificates
            elif command -v dnf >/dev/null 2>&1; then
                sudo_run dnf install -y python3 curl ca-certificates
            elif command -v pacman >/dev/null 2>&1; then
                sudo_run pacman -S --needed --noconfirm python curl ca-certificates
            else
                echo 'Automatic Python provisioning supports Debian/Ubuntu, Fedora and Arch. Install Python 3.9+ and rerun.' >&2
                exit 1
            fi
            ;;
        *) echo 'Use bootstrap/setup.ps1 on Windows.' >&2; exit 1 ;;
    esac
fi
python_ready || { echo 'Python provisioning failed; Python 3.9+ is required.' >&2; exit 1; }
# A checked-out copy works offline, including read-only previews.
case "$0" in
    */setup.sh|setup.sh)
        if [ -f "$(dirname "$0")/cockpit.py" ]; then
            exec "$python_command" "$(dirname "$0")/cockpit.py" "$@"
        fi
        ;;
esac
command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo 'tar is required.' >&2; exit 1; }
ref=${DEV_COCKPIT_REF:-main}
case "$ref" in ''|*[!a-zA-Z0-9._-]*) echo 'Invalid DEV_COCKPIT_REF; use a tag or commit SHA.' >&2; exit 1;; esac
# Preview never creates a persistent cache. Temporary files are removed on exit.
scratch=$(mktemp -d "${TMPDIR:-/tmp}/dev-cockpit.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT HUP INT TERM
if [ "$mutate" -eq 0 ]; then cache="$scratch/cache"; fi
# Resolve moving refs once; archives use immutable commits and checksum-addressed
# metadata to detect a damaged local cache. Optional trusted hash verifies origin.
if [ "${#ref}" -eq 40 ] && ! printf '%s' "$ref" | LC_ALL=C grep '[^0-9a-f]' >/dev/null; then
    revision=$ref
else
    fetch "https://api.github.com/repos/UtkarshBhardwaj007/dev-cockpit/commits/$ref" "$scratch/revision.json"
    revision=$("$python_command" -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha"])' "$scratch/revision.json")
fi
case "$revision" in ''|*[!0-9a-f]*) echo 'Invalid repository revision response' >&2; exit 1;; esac
[ "${#revision}" -eq 40 ] || { echo 'Invalid repository commit SHA' >&2; exit 1; }
mkdir -p "$cache/archives"
archive="$cache/archives/$revision.tar.gz"
expected=${DEV_COCKPIT_SHA256:-}
if [ -z "$expected" ] && [ -f "$archive.sha256" ]; then expected=$(cat "$archive.sha256"); fi
if [ ! -f "$archive" ] || [ -z "$expected" ] || [ "$(sha_file "$archive")" != "$expected" ]; then
    temporary=$(mktemp "$cache/archives/.repository.XXXXXXXX")
    fetch "https://codeload.github.com/UtkarshBhardwaj007/dev-cockpit/tar.gz/$revision" "$temporary"
    actual=$(sha_file "$temporary")
    if [ -n "${DEV_COCKPIT_SHA256:-}" ] && [ "$actual" != "$DEV_COCKPIT_SHA256" ]; then
        rm -f "$temporary"; echo 'Repository archive checksum mismatch' >&2; exit 1
    fi
    mv "$temporary" "$archive"
    printf '%s\n' "$actual" > "$archive.sha256"
fi
mkdir "$scratch/repo"
tar -xzf "$archive" --strip-components=1 -C "$scratch/repo"
# One-line/piped installs run from a temporary scratch that is removed on exit;
# persist a copy of the runtime so `dev` keeps working after this installer exits.
export DEV_COCKPIT_DEPLOY_RUNTIME=1
"$python_command" "$scratch/repo/bootstrap/cockpit.py" "$@"
