"""Unified Dev Cockpit CLI.

The single entrypoint for both the setup launchers (bootstrap/setup.sh and
bootstrap/setup.ps1) and the interactive shell functions (dev, dev-doctor,
dev-update, ...). Setup flags and subcommands are accepted here; all work is
delegated to the dev_cockpit package modules so there is exactly one source of
truth for package, configuration and workspace logic.
"""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

from . import configuration, mobile, packages, runtime


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROFILES = ("core", "cockpit", "terminal")


def host_platform():
    names = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
    try:
        return names[platform.system()]
    except KeyError:
        raise ValueError("Unsupported OS; supported targets are macOS, Linux and Windows.")


PROFILES = ("core", "cockpit", "terminal", "history", "extras")


def _base_parser():
    parser = argparse.ArgumentParser(prog="dev-cockpit", description="Reproducible AI-first developer environment.")
    parser.add_argument("--platform", choices=["macos", "linux", "windows"], help="Preview another OS; mutations require the host OS")
    parser.add_argument("--profile", action="append", choices=list(PROFILES), help="Repeatable; default: core, cockpit, terminal")
    parser.add_argument("--home", type=Path, help="Isolated config target for testing; ignores XDG/APPDATA overrides")
    parser.add_argument("--dry-run", action="store_true", help="Explicit read-only preview; no packages or config are changed")
    parser.add_argument("--install", action="store_true", help="Install selected missing packages")
    parser.add_argument("--apply-config", action="store_true", help="Create or safely update themed config and shell activation")
    parser.add_argument("--activate-shell", action="store_true", help="Ensure shell profile activation blocks exist (idempotent)")
    parser.add_argument("--uninstall-config", action="store_true", help="Remove unchanged project-owned config only; leave packages installed")
    parser.add_argument("--doctor", action="store_true", help="Check selected binaries on PATH and report config status")
    parser.add_argument("--force-config", action="store_true", help="Repair project-created config even if edited (previous content is backed up)")
    return parser


def _setup(argv):
    parser = _base_parser()
    args = parser.parse_args(argv)
    actual = host_platform()
    target = args.platform or actual
    mutation = args.install or args.apply_config or args.activate_shell or args.uninstall_config
    if args.dry_run and mutation:
        parser.error("--dry-run cannot be combined with mutation flags")
    if args.uninstall_config and (args.install or args.apply_config or args.activate_shell):
        parser.error("--uninstall-config cannot be combined with installation")
    if args.doctor and mutation:
        parser.error("--doctor cannot be combined with mutation flags")
    if mutation and target != actual:
        parser.error("Cross-platform simulation is preview-only")
    if args.home and args.install:
        parser.error("--home isolates config only; it cannot sandbox package installation")
    home = args.home.absolute() if args.home else Path.home()
    profiles = args.profile or list(DEFAULT_PROFILES)
    root = ROOT
    if os.environ.get("DEV_COCKPIT_DEPLOY_RUNTIME") and args.install:
        root = runtime.deploy_runtime(ROOT, home)
    plan = packages.package_plan(target, profiles, root=root)
    mode = "apply" if mutation else ("doctor" if args.doctor else "preview")
    print("Dev Cockpit |", target, "|", ", ".join(profiles), "|", mode)
    if args.doctor:
        if target != actual:
            parser.error("--doctor checks the host OS only")
        return packages.doctor(plan, home=home)
    if not args.uninstall_config and args.apply_config:
        configuration.manage_config(home, target, apply=True, use_environment=not args.home, root=root, force=args.force_config, profiles=profiles)
    elif args.activate_shell:
        # Idempotent: only creates/updates the owned shell activation blocks.
        configuration.manage_config(home, target, apply=True, use_environment=not args.home, root=root, force=args.force_config, profiles=profiles)
    packages.run_packages(plan, install=args.install, home=home)
    if args.install:
        _launch_gesture_bridge(target, home)
    if args.uninstall_config:
        # apply=True is required: manage_config only performs removal when apply is set.
        configuration.manage_config(home, target, apply=True, uninstall=True, use_environment=not args.home, root=root)
    if args.install:
        configuration.generate_completions(home, target, use_environment=not args.home, force=False)
    if args.apply_config or args.activate_shell:
        print("Configuration and shell activation applied. Existing user profile content outside the managed block is preserved.")
    return 0


def _launch_gesture_bridge(target, home):
    """Start Hammerspoon after install so the gestures bridge is live.

    No-op outside macOS; the Accessibility grant itself is manual and cannot
    be verified from here.
    """
    message = packages.launch_gesture_bridge(target, home=home)
    if message:
        print(message + ". Grant Hammerspoon Accessibility once (System Settings > "
              "Privacy & Security > Accessibility), then quit and reopen Hammerspoon "
              "so it picks up the grant.")


def _cmd_launch(argv):
    # Full cockpit launch: install + configure on the host, safely. Repair is the
    # default so one command picks up every managed update, including Herdr.
    return _setup(["--install", "--apply-config", "--force-config", *argv])


def _cmd_doctor(argv):
    parser = argparse.ArgumentParser(prog="dev-doctor")
    parser.add_argument("--profile", action="append", choices=list(PROFILES))
    parser.add_argument("--home", type=Path)
    args = parser.parse_args(argv)
    home = args.home.absolute() if args.home else Path.home()
    target = host_platform()
    profiles = args.profile or list(DEFAULT_PROFILES)
    plan = packages.package_plan(target, profiles)
    code = packages.doctor(plan, home=home)
    for entry in configuration.configuration_status(home, target, profiles=profiles):
        print("CONFIG", entry.get("status", "?"), entry["path"],
              ("- " + entry["detail"]) if entry.get("detail") else "")
        if entry.get("status") == "error":
            code = 1
    if target == "macos":
        app = packages.gesture_bridge_app(home)
        print("GESTURE", "FOUND" if app else "MISSING", "Hammerspoon.app", str(app) if app else "")
        if not app:
            code = 1
        print("GESTURE", "MANUAL", "Accessibility must be granted by hand in System Settings > "
              "Privacy & Security > Accessibility, then quit and reopen Hammerspoon")
    return code


def _cmd_update(argv):
    parser = argparse.ArgumentParser(prog="dev-update")
    parser.add_argument("--profile", action="append", choices=list(PROFILES))
    parser.add_argument("--home", type=Path)
    parser.add_argument("--completions", action="store_true", help="Force regeneration (by default only stale completions refresh)")
    args = parser.parse_args(argv)
    home = args.home.absolute() if args.home else Path.home()
    target = host_platform()
    configuration.manage_config(home, target, apply=True, use_environment=not args.home, force=True, profiles=args.profile or list(DEFAULT_PROFILES))
    configuration.generate_completions(home, target, use_environment=not args.home, force=args.completions)
    plan = packages.package_plan(target, args.profile or list(DEFAULT_PROFILES))
    packages.run_packages(plan, install=True, home=home)
    _launch_gesture_bridge(target, home)
    print("Update complete.")
    return 0


def _cmd_uninstall(argv):
    parser = argparse.ArgumentParser(prog="dev-uninstall")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Preview uninstall without removing anything")
    args = parser.parse_args(argv)
    home = args.home.absolute() if args.home else Path.home()
    target = host_platform()
    # apply=True performs removal; dry-run previews the plan without removing.
    configuration.manage_config(home, target, apply=not args.dry_run, uninstall=True, use_environment=not args.home)
    return 0


def _cmd_completions(argv):
    parser = argparse.ArgumentParser(prog="dev-completions")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    home = args.home.absolute() if args.home else Path.home()
    configuration.generate_completions(home, host_platform(), use_environment=not args.home, force=args.force)
    return 0


def _cmd_mobile(argv):
    parser = argparse.ArgumentParser(prog="dev-mobile")
    parser.parse_args(argv)
    return mobile.show()


def _run_intelligence(kind, argv):
    from . import intelligence
    return intelligence.main([kind, *argv])


def _cmd_memory(argv):
    return _run_intelligence("memory", argv)


def _cmd_graph(argv):
    return _run_intelligence("graph", argv)


def _cmd_open(argv):
    parser = argparse.ArgumentParser(prog="dev-open", description="Open a project in a Herdr cockpit workspace.")
    parser.add_argument("project", nargs="?", type=Path, default=Path.cwd(),
                        help="Project directory to open (default: current directory)")
    args = parser.parse_args(argv)
    from . import workspace
    return workspace.launch(args.project.resolve())




SUBCOMMANDS = {
    "launch": _cmd_launch,
    "doctor": _cmd_doctor,
    "update": _cmd_update,
    "uninstall": _cmd_uninstall,
    "completions": _cmd_completions,
    "mobile": _cmd_mobile,
    "memory": _cmd_memory,
    "graph": _cmd_graph,
    "open": _cmd_open,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SUBCOMMANDS:
        return SUBCOMMANDS[argv[0]](argv[1:])
    return _setup(argv)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)
