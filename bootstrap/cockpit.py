#!/usr/bin/env python3
"""Small, dependency-free bootstrap prototype. Preview is the default."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def host_platform():
    names = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
    try:
        return names[platform.system()]
    except KeyError:
        raise ValueError("Unsupported OS; supported targets are macOS, Linux and Windows.")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cockpit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def reject_links(path):
    # Never traverse existing symlinks or Windows junctions when managing files.
    for entry in (path, *path.parents):
        reparse = entry.exists() and bool(getattr(entry.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        if entry.is_symlink() or reparse:
            raise ValueError("Refusing symlink/junction in managed path: " + str(entry))


def config_targets(home, target, use_environment=False):
    # Resolve the chosen root once (macOS /var and /tmp are OS symlinks).
    # Symlinks below it remain visible and are rejected before writes.
    home = home.resolve()
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) if use_environment else home / ".config"
    appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) if use_environment else home / "AppData/Roaming"
    config = appdata if target == "windows" else xdg
    # All targets are enumerated here; the ownership ledger cannot invent paths.
    paths = {
        "config/starship/starship.toml": config / "dev-cockpit/starship.toml",
        "config/herdr/config.toml": config / "herdr/config.toml",
        "config/omp/config.yml": home / ".omp/agent/config.yml",
        "config/yazi/theme.toml": config / ("yazi/config/theme.toml" if target == "windows" else "yazi/theme.toml"),
    }
    if target == "windows":
        paths["config/terminals/wezterm.lua"] = home / ".wezterm.lua"
        paths["config/shell/init.ps1"] = config / "dev-cockpit/init.ps1"
    else:
        paths["config/terminals/ghostty"] = config / "ghostty/config"
        paths["config/shell/init.sh"] = config / "dev-cockpit/init.sh"
    return paths, config / "dev-cockpit/ownership.json"


def manage_config(home, target, apply=False, uninstall=False, use_environment=False):
    targets, ledger = config_targets(home, target, use_environment)
    reject_links(ledger)
    for dest in targets.values():
        reject_links(dest)
    state = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else {}
    if not isinstance(state, dict):
        raise ValueError("Invalid ownership ledger; restore or inspect " + str(ledger))
    updates = []
    for source, dest in targets.items():
        key = str(dest)
        current = dest.read_bytes() if dest.exists() else None
        old_hash = state.get(key)
        if uninstall:
            if current is not None and old_hash == digest(current):
                updates.append(("remove", dest, None))
            elif old_hash:
                print("PRESERVE changed or missing file:", dest)
            continue
        desired = (ROOT / source).read_bytes()
        if current is None:
            updates.append(("create", dest, desired))
        elif old_hash and old_hash == digest(current):
            if current != desired:
                updates.append(("update", dest, desired))
            else:
                print("UNCHANGED", dest)
        else:
            print("PRESERVE existing/user-edited file:", dest)
    for action, dest, data in updates:
        print(("APPLY" if apply else "PLAN"), action, dest)
        if apply:
            if action == "remove":
                dest.unlink()
                state.pop(str(dest), None)
            else:
                atomic_write(dest, data)
                state[str(dest)] = digest(data)
            # Persist after each change: an interrupted run never owns a file
            # it did not finish writing. A crash between writes preserves it.
            atomic_write(ledger, (json.dumps(state, indent=2) + "\n").encode())
    return updates


def package_plan(target, profiles):
    manifest = json.loads((ROOT / "manifests/tools.json").read_text(encoding="utf-8"))
    result = []
    for tool in manifest["tools"]:
        if tool["profile"] not in profiles:
            continue
        spec = tool["platforms"].get(target)
        if spec is None:
            continue
        if "manual" in spec:
            result.append((tool, None, spec["manual"]))
        elif target == "windows":
            result.append((tool, ["winget", "install", "--exact", "--id", spec["package"], "--source", "winget", "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"], None))
        else:
            result.append((tool, ["brew", "install", *(["--cask"] if spec.get("cask") else []), spec["package"]], None))
    return result


def run_packages(plan, install=False):
    pending = []
    for tool, command, manual in plan:
        if shutil.which(tool["binary"]):
            print("PRESENT", tool["id"], "(version compatibility not yet enforced)")
        elif command:
            print("PACKAGE", tool["id"], ":", shlex.join(command))
            pending.append(command)
        else:
            print("MANUAL", tool["id"], ":", manual)
            if install:
                raise ValueError("Selected profile requires a manual adapter; choose core or follow the listed upstream instructions first.")
    if install:
        # Preflight every adapter before installing the first package.
        for command in pending:
            if not shutil.which(command[0]):
                raise ValueError("Missing " + command[0] + "; install the package manager and reopen your shell first.")
        for command in pending:
            subprocess.run(command, check=True)
        if pending:
            print("Packages installed. Reopen your shell to refresh PATH, then run --doctor.")


def doctor(plan):
    missing = []
    for tool, _, _ in plan:
        executable = shutil.which(tool["binary"])
        print("FOUND" if executable else "MISSING", tool["id"], executable or "")
        if not executable:
            missing.append(tool["id"])
    print("Doctor checks PATH presence only; GUI, authentication and version checks remain separate.")
    return 1 if missing else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["macos", "linux", "windows"], help="Preview another OS; mutations require the host OS")
    parser.add_argument("--profile", action="append", choices=["core", "cockpit", "terminal", "history"], help="Repeatable; default: core")
    parser.add_argument("--home", type=Path, help="Isolated config target for testing; ignores XDG/APPDATA overrides")
    parser.add_argument("--dry-run", action="store_true", help="Explicit read-only preview (the default)")
    parser.add_argument("--install", action="store_true", help="Install selected missing packages")
    parser.add_argument("--apply-config", action="store_true", help="Create or safely update themed config files")
    parser.add_argument("--uninstall-config", action="store_true", help="Remove unchanged project-owned config only; leave packages installed")
    parser.add_argument("--doctor", action="store_true", help="Check selected binaries on PATH")
    args = parser.parse_args(argv)
    actual = host_platform()
    target = args.platform or actual
    mutation = args.install or args.apply_config or args.uninstall_config
    if args.dry_run and mutation:
        parser.error("--dry-run cannot be combined with mutation flags")
    if args.uninstall_config and (args.install or args.apply_config):
        parser.error("--uninstall-config cannot be combined with installation")
    if args.doctor and mutation:
        parser.error("--doctor cannot be combined with mutation flags")
    if mutation and target != actual:
        parser.error("Cross-platform simulation is preview-only")
    if args.home and args.install:
        parser.error("--home isolates config only; it cannot sandbox package installation")
    home = args.home.absolute() if args.home else Path.home()
    profiles = args.profile or ["core"]
    plan = package_plan(target, profiles)
    print("Dev Cockpit |", target, "|", ", ".join(profiles), "|", "apply" if mutation else "preview")
    if args.doctor:
        if target != actual:
            parser.error("--doctor checks the host OS only")
        return doctor(plan)
    if not args.uninstall_config:
        # Validate config paths and state before any package action.
        if args.apply_config:
            manage_config(home, target, use_environment=not args.home)
        run_packages(plan, install=args.install)
    manage_config(home, target, apply=args.apply_config or args.uninstall_config,
                  uninstall=args.uninstall_config, use_environment=not args.home)
    if args.apply_config:
        print("Shell profiles were preserved. See docs/customization.md for explicit activation.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)
