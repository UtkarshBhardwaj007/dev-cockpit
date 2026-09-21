"""Conservative configuration ownership, profile integration and completion caching.

Only enumerated destinations can be changed. Existing configuration files are
preserved; shell profiles receive individually owned, reversible blocks. The
ledger is an aid to ownership, never authority to write arbitrary paths.
"""
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
BEGIN = b"# >>> dev-cockpit >>>"
END = b"# <<< dev-cockpit <<<"
SCHEMA = 2


def digest(data):
    return hashlib.sha256(data).hexdigest()


def linked_entry(path):
    """Return the first symlink/junction in path or its parents, else None."""
    for entry in (Path(path), *Path(path).parents):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            return entry
    return None


def reject_links(path):
    entry = linked_entry(path)
    if entry is not None:
        raise ValueError("Refusing symlink/junction in managed path: " + str(entry))


def atomic_write(path, data):
    """Replace with a flushed sibling; preserve mode on existing private files."""
    path = Path(path)
    reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=".cockpit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        reject_links(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def configuration_lock(directory):
    """Fail closed on a concurrent or interrupted installer; never guess stale PID."""
    directory = Path(directory)
    reject_links(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "configuration.lock"
    reject_links(lock)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("Configuration is locked: " + str(lock) + ". Wait for the other setup; after a crash, inspect this file and remove it only when no setup is running.") from error
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid()}, stream)
        yield
    finally:
        lock.unlink()


def _bases(home, target, use_environment=False):
    if target not in ("macos", "linux", "windows"):
        raise ValueError("Unsupported configuration platform: " + target)
    # Resolve the selected root only, allowing macOS's system /var -> /private/var.
    home = Path(home).resolve()
    config = home / ("AppData/Roaming" if target == "windows" else ".config")
    if use_environment:
        configured = os.environ.get("APPDATA" if target == "windows" else "XDG_CONFIG_HOME")
        if configured:
            config = Path(configured)
            if not config.is_absolute():
                raise ValueError("Configuration root must be absolute: " + str(config))
    return home, config


def config_targets(home, target, use_environment=False, profiles=None):
    home, config = _bases(home, target, use_environment)
    owned = config / "dev-cockpit"
    # Atuin deliberately follows XDG on Windows as well as Unix.
    atuin_config = home / ".config/atuin"
    if use_environment:
        atuin_xdg = os.environ.get("XDG_CONFIG_HOME")
        atuin_config = Path(os.environ.get("ATUIN_CONFIG_DIR") or (str(Path(atuin_xdg) / "atuin") if atuin_xdg else str(atuin_config)))
        if not atuin_config.is_absolute():
            raise ValueError("Atuin configuration root must be absolute")
    lazygit = config / "lazygit/config.yml"
    if target == "macos" and not (use_environment and os.environ.get("XDG_CONFIG_HOME")):
        lazygit = home / "Library/Application Support/lazygit/config.yml"
    elif target == "windows":
        localappdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local"))) if use_environment else home / "AppData/Local"
        if not localappdata.is_absolute():
            raise ValueError("LOCALAPPDATA must be absolute")
        candidates = [localappdata / "lazygit/config.yml", config / "lazygit/config.yml", config / "jesseduffield/lazygit/config.yml"]
        lazygit = next((path for path in candidates if path.exists()), candidates[0])
    paths = {
        "config/starship/starship.toml": owned / "starship.toml",
        "config/herdr/config.toml": config / "herdr/config.toml",
        "config/omp/config.yml": home / ".omp/agent/config.yml",
        "config/yazi/theme.toml": config / ("yazi/config/theme.toml" if target == "windows" else "yazi/theme.toml"),
        "config/yazi/yazi.toml": config / ("yazi/config/yazi.toml" if target == "windows" else "yazi/yazi.toml"),
        "config/yazi/keymap.toml": config / ("yazi/config/keymap.toml" if target == "windows" else "yazi/keymap.toml"),
        "config/atuin/config.toml": atuin_config / "config.toml",
        "config/lazygit/config.yml": lazygit,
        "config/bat/config": config / "bat/config",
        "config/git/delta.gitconfig": owned / "delta.gitconfig",
    }
    if target == "windows":
        terminal_candidates = [home / ".wezterm.lua", home / ".config/wezterm/wezterm.lua"]
        if use_environment and os.environ.get("WEZTERM_CONFIG_FILE"):
            terminal_candidates.insert(0, Path(os.environ["WEZTERM_CONFIG_FILE"]))
        if any(not path.is_absolute() for path in terminal_candidates):
            raise ValueError("WezTerm config path must be absolute")
        paths["config/terminals/wezterm.lua"] = next((path for path in terminal_candidates if path.exists()), terminal_candidates[0])
        paths["config/shell/init.ps1"] = owned / "init.ps1"
    else:
        terminal_candidates = [config / "ghostty/config.ghostty", config / "ghostty/config"]
        if target == "macos":
            terminal_candidates += [home / "Library/Application Support/com.mitchellh.ghostty/config.ghostty", home / "Library/Application Support/com.mitchellh.ghostty/config"]
        paths["config/terminals/ghostty"] = next((path for path in reversed(terminal_candidates) if path.exists()), config / "ghostty/config")
        paths["config/shell/init.sh"] = owned / "init.sh"
        paths["config/btop/btop.conf"] = config / "btop/btop.conf"
    # The Hammerspoon pinch-to-zoom bridge is a default macOS capability.
    # Linux and Windows deliberately have no equivalent bridge.
    if target == "macos":
        paths["config/hammerspoon/init.lua"] = home / ".hammerspoon/init.lua"
    return paths, owned / "ownership.json"


def _documents(home, use_environment):
    if use_environment and os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        # CSIDL_PERSONAL honors OneDrive / redirected Documents.
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return home / "Documents"


def profile_targets(home, target, use_environment=False):
    home, _ = _bases(home, target, use_environment)
    if target == "windows":
        documents = _documents(home, use_environment)
        return {documents / "PowerShell/profile.ps1": "powershell", documents / "WindowsPowerShell/profile.ps1": "powershell"}
    zdir = Path(os.environ.get("ZDOTDIR", str(home))) if use_environment else home
    if not zdir.is_absolute():
        raise ValueError("ZDOTDIR must be absolute")
    login = next((home / name for name in (".bash_profile", ".bash_login", ".profile") if (home / name).exists()), home / ".bash_profile")
    return {home / ".bashrc": "bash", login: "bash", zdir / ".zshrc": "zsh"}


def _state(path):
    reject_links(path)
    if not path.exists():
        return {"schema": SCHEMA, "files": {}, "blocks": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid ownership ledger: " + str(path)) from error
    if not isinstance(value, dict):
        raise ValueError("Invalid ownership ledger: " + str(path))
    if "schema" not in value:  # Migrate prototype's file-hash ledger without adopting files.
        if not all(isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v) for k, v in value.items()):
            raise ValueError("Invalid legacy ownership ledger: " + str(path))
        return {"schema": SCHEMA, "files": value, "blocks": {}}
    if value.get("schema") != SCHEMA or not isinstance(value.get("files"), dict) or not isinstance(value.get("blocks"), dict):
        raise ValueError("Unsupported or invalid ownership ledger: " + str(path))
    for key, item in value["files"].items():
        if not isinstance(key, str) or not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item):
            raise ValueError("Invalid file ownership record: " + str(path))
    for key, item in value["blocks"].items():
        if not isinstance(key, str) or not isinstance(item, dict) or not isinstance(item.get("hash"), str) or not re.fullmatch(r"[a-f0-9]{64}", item["hash"]) or not isinstance(item.get("created"), bool) or item.get("prefix") not in ("", "\n", "\r\n"):
            raise ValueError("Invalid profile ownership record: " + str(path))
    return value


def _save_state(path, state):
    desired = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
    if not path.exists() or path.read_bytes() != desired:
        atomic_write(path, desired)


def _block_span(content):
    lines = content.splitlines(keepends=True)
    starts, ends, offset = [], [], 0
    for line in lines:
        if line.rstrip(b"\r\n") == BEGIN:
            starts.append(offset)
        if line.rstrip(b"\r\n") == END:
            ends.append(offset + len(line))
        offset += len(line)
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("Ambiguous dev-cockpit profile markers; preserve and repair the profile manually")
    return starts[0], ends[0]


def _quote_ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def _profile_content(raw, shell):
    """Normalize for marker operations, retaining the original profile encoding."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16-le" if raw.startswith(b"\xff\xfe") else "utf-16-be"
        bom = raw[:2]
        return raw[2:].decode(encoding).encode(), lambda data: bom + data.decode().encode(encoding)
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") or (not raw and shell == "powershell") else b""
    content = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    content.decode("utf-8")  # Refuse lossy rewrites of an unknown encoding.
    return content, lambda data: bom + data


def _profile_block(content, shell, directory, extra_context=b""):
    span = _block_span(content)
    outside = content[:span[0]] + content[span[1]:] if span else content
    # Ignore ordinary comments. A conservative match can skip a hook but never
    # risks double-registering an existing framework's prompt or history hooks.
    text = "\n".join(line for line in (outside + b"\n" + extra_context).decode("utf-8-sig").splitlines() if not line.lstrip().startswith("#"))
    rules = {
        "STARSHIP": r"starship\s+init|oh-my-posh|oh-my-zsh|powerlevel|p10k|prezto|ZSH_THEME\s*=|(?:^|\s)PS1=|function\s+(?:global:)?prompt",
        "ZOXIDE": r"zoxide\s+init",
        "MISE": r"mise\s+activate",
        "ATUIN": r"atuin\s+init",
        "DIRENV": r"direnv\s+hook",
        "FZF": r"fzf\s+--(?:bash|zsh)|fzf\.(?:bash|zsh)|fzf-tab|PSFzf",
        "PSREADLINE": r"Set-PSReadLineOption|Set-PSReadLineKeyHandler",
    }
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    lines = [BEGIN.decode(), "# Managed activation only. Edit preferences outside these markers."]
    skips = [name for name, pattern in rules.items() if re.search(pattern, text, re.I | re.M)]
    if shell == "powershell":
        lines += ["$env:DEV_COCKPIT_CONFIG_DIR = " + _quote_ps(directory)]
        lines += ["$env:DEV_COCKPIT_SKIP_" + name + " = '1'" for name in skips]
        init = _quote_ps(directory / "init.ps1")
        lines += ["if (Test-Path -LiteralPath " + init + ") { . " + init + " }"]
    else:
        lines += ["DEV_COCKPIT_CONFIG_DIR=" + shlex.quote(str(directory))]
        lines += ["DEV_COCKPIT_SKIP_" + name + "=1" for name in skips]
        init = shlex.quote(str(directory / "init.sh"))
        lines += ["[ ! -r " + init + " ] || . " + init]
    lines += [END.decode()]
    return newline.join(line.encode() for line in lines) + newline


def _render_environment(directory, target, root, python_executable, home):
    values = {"DEV_COCKPIT_CONFIG_DIR": str(directory), "DEV_COCKPIT_USER_HOME": str(Path(home).resolve()), "DEV_COCKPIT_ROOT": str(Path(root).resolve()), "DEV_COCKPIT_PYTHON": str(Path(python_executable or sys.executable).resolve())}
    if target == "windows":
        return directory / "environment.ps1", ("\n".join("$env:" + key + " = " + _quote_ps(value) for key, value in values.items()) + "\n").encode("utf-8-sig")
    return directory / "environment.sh", ("\n".join("export " + key + "=" + shlex.quote(value) for key, value in values.items()) + "\n").encode()


def _backup(directory, path, data):
    backup = directory / "backups" / digest(str(path).encode()) / (digest(data) + ".bak")
    reject_links(backup)
    if backup.exists():
        if backup.read_bytes() != data:
            raise ValueError("Configuration backup has changed: " + str(backup))
    else:
        atomic_write(backup, data)


def _completion_removal_plan(directory):
    cache = directory / "completions/manifest.json"
    reject_links(cache)
    if not cache.exists():
        return []
    state = json.loads(cache.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Invalid completion manifest: " + str(cache))
    changes = []
    remaining = dict(state)
    # Construct the allowed filenames ourselves, ignoring any unknown ledger keys.
    for shell in ["bash", "zsh", "powershell"]:
        for tool, command in COMPLETION_COMMANDS.items():
            if command(shell) is None:
                continue
            filename = "_" + tool if shell == "zsh" else tool + (".ps1" if shell == "powershell" else ".bash")
            key = shell + "/" + filename
            destination = directory / "completions" / key
            reject_links(destination)
            record = state.get(key)
            if record is None:
                continue
            if not isinstance(record, dict) or not isinstance(record.get("hash"), str):
                raise ValueError("Invalid completion record: " + key)
            if destination.exists() and digest(destination.read_bytes()) == record["hash"]:
                changes.append(("remove", destination, None))
                remaining.pop(key)
            elif destination.exists():
                print("PRESERVE user-edited completion:", destination)
    if remaining != state:
        changes.append(("update", cache, (json.dumps(remaining, indent=2, sort_keys=True) + "\n").encode()) if remaining else ("remove", cache, None))
    return changes


def _report_linked_profile(destination, shell, directory, uninstall):
    """Never write through a linked profile; tell the user what to add by hand."""
    print("PRESERVE symlinked shell profile (managed outside dev-cockpit):", destination, "->", destination.resolve())
    if uninstall:
        return
    try:
        current, _ = _profile_content(destination.read_bytes(), shell) if destination.is_file() else (b"", None)
        if _block_span(current):
            return
    except (OSError, ValueError):  # UnicodeDecodeError is a ValueError
        return
    print("MANUAL add this activation block to", destination.resolve(), "(the real file behind " + str(destination) + "), then open a new shell:")
    print(_profile_block(current, shell, directory).decode().rstrip("\r\n"))


def manage_config(home, target, apply=False, uninstall=False, use_environment=False, root=ROOT, python_executable=None, force=False, profiles=None):
    """Preview/apply or remove only unchanged owned files and profile blocks.

    With force=True, files this project created are repaired even when they were
    edited afterwards; the previous content is backed up first. Files the user
    created themselves are never touched, and profile blocks stay conservative.
    """
    paths, ledger = config_targets(home, target, use_environment, profiles)
    profiles = profile_targets(home, target, use_environment)
    directory = ledger.parent
    environment, environment_data = _render_environment(directory, target, root, python_executable, home)
    # Validate every destination and the complete state before the first write.
    # dev-cockpit's own state directory must be real. A link anywhere else (for
    # example a stow/chezmoi/home-manager managed ~/.bashrc) marks a user-managed
    # file: it is preserved and never written through, and setup continues.
    linked = {}
    for destination in [ledger, environment, *paths.values(), *profiles]:
        entry = linked_entry(destination)
        if entry is not None:
            if destination == ledger or directory in destination.parents:
                raise ValueError("Refusing symlink/junction in dev-cockpit state path: " + str(entry) + ". The dev-cockpit config directory must be a real directory.")
            linked[destination] = entry
            continue
        if destination.exists() and not destination.is_file():
            raise ValueError("Configuration destination is not a regular file: " + str(destination))
    _state(ledger)
    changes = []
    with configuration_lock(directory) if apply else nullcontext():
        state = _state(ledger)
        completion_changes = _completion_removal_plan(directory) if uninstall else []
        desired_files = {destination: (Path(root) / source).read_bytes() for source, destination in paths.items()}
        desired_files[environment] = environment_data
        planned = []
        for destination, desired in desired_files.items():
            key = str(destination)
            if destination in linked:
                print("PRESERVE symlinked file (managed outside dev-cockpit):", destination, "->", destination.resolve())
                continue
            current = destination.read_bytes() if destination.exists() else None
            owned = current is not None and state["files"].get(key) == digest(current)
            if uninstall:
                if owned:
                    planned.append(("remove", destination, None, "files", None))
                elif key in state["files"]:
                    print("PRESERVE changed/missing file:", destination)
                continue
            # OMP owns its config and may rewrite it at runtime, so never replace
            # an existing OMP file. Herdr only rewrites config.toml when the user
            # changes settings, which changes the hash and is preserved as edited.
            create_only = destination == paths["config/omp/config.yml"]
            if current is None:
                planned.append(("create", destination, desired, "files", digest(desired)))
            elif current == desired and owned:
                pass
            elif owned and not create_only:
                planned.append(("update", destination, desired, "files", digest(desired)))
            elif force and not create_only and key in state["files"]:
                planned.append(("repair", destination, desired, "files", digest(desired)))
            else:
                print("PRESERVE existing/user-edited file:", destination)
        for destination, shell in profiles.items():
            key = str(destination)
            if destination in linked:
                _report_linked_profile(destination, shell, directory, uninstall)
                continue
            raw = destination.read_bytes() if destination.exists() else b""
            current, encode = _profile_content(raw, shell)
            extra_context = b""
            if shell == "powershell":
                companion = destination.parent / "Microsoft.PowerShell_profile.ps1"
                if companion.is_file():
                    extra_context, _ = _profile_content(companion.read_bytes(), shell)
            span = _block_span(current)
            record = state["blocks"].get(key)
            if span:
                existing = current[span[0]:span[1]]
                if not record or record["hash"] != digest(existing):
                    print("PRESERVE user-edited/unowned activation block:", destination)
                    continue
                if uninstall:
                    start = span[0]
                    prefix = record["prefix"].encode()
                    if prefix and current[:start].endswith(prefix):
                        start -= len(prefix)
                    desired = current[:start] + current[span[1]:]
                    action = "remove" if record["created"] and not desired else "update"
                    planned.append((action, destination, None if action == "remove" else encode(desired), "blocks", None))
                else:
                    block = _profile_block(current, shell, directory, extra_context)
                    if existing != block:
                        desired = current[:span[0]] + block + current[span[1]:]
                        planned.append(("update", destination, encode(desired), "blocks", dict(record, hash=digest(block))))
            elif record:
                print("PRESERVE manually removed activation block:", destination)
            elif not uninstall:
                block = _profile_block(current, shell, directory, extra_context)
                prefix = b"" if not current or current.endswith(b"\n") else (b"\r\n" if b"\r\n" in current else b"\n")
                record = {"hash": digest(block), "prefix": prefix.decode(), "created": not destination.exists()}
                planned.append(("update" if current else "create", destination, encode(current + prefix + block), "blocks", record))
        # Planning every profile before writes catches malformed markers before
        # touching any config or package-independent profile file.
        for action, destination, data, section, ownership in planned:
            print("APPLY" if apply else "PLAN", action, destination)
            changes.append((action, destination, data))
            if not apply:
                continue
            if destination.exists():
                _backup(directory, destination, destination.read_bytes())
            if action == "remove":
                destination.unlink()
            else:
                atomic_write(destination, data)
            if ownership is None:
                state[section].pop(str(destination), None)
            else:
                state[section][str(destination)] = ownership
            # On a crash between config and ledger writes, the next run treats
            # the changed config as unowned and preserves it.
            _save_state(ledger, state)
        for action, destination, data in completion_changes:
            print("APPLY" if apply else "PLAN", action, destination)
            changes.append((action, destination, data))
            if apply:
                if action == "remove":
                    destination.unlink()
                else:
                    atomic_write(destination, data)
    return changes


def configuration_status(home, target, use_environment=False, profiles=None):
    paths, ledger = config_targets(home, target, use_environment, profiles)
    result = []
    try:
        state = _state(ledger)
        profiles = profile_targets(home, target, use_environment)
        reject_links(ledger)
        for path in [*paths.values(), *profiles]:
            if linked_entry(path) is not None:
                result.append({"path": str(path), "status": "symlinked", "detail": "managed outside dev-cockpit"})
                continue
            status = "missing" if not path.exists() else "preserved"
            if path.exists():
                content = path.read_bytes()
                if state["files"].get(str(path)) == digest(content):
                    status = "managed"
                elif str(path) in state["blocks"]:
                    content, _ = _profile_content(content, profiles[path])
                    span = _block_span(content)
                    status = "managed" if span and state["blocks"][str(path)]["hash"] == digest(content[span[0]:span[1]]) else "edited"
            result.append({"path": str(path), "status": status})
    except (OSError, ValueError) as error:
        result.append({"path": str(ledger), "status": "error", "detail": str(error)})
    return result


COMPLETION_COMMANDS = {
    "gh": lambda shell: ["completion", "-s", shell],
    "herdr": lambda shell: ["completion", shell],
    "omp": lambda shell: ["completions", shell] if shell != "powershell" else None,
    "starship": lambda shell: ["completions", shell],
}


def generate_completions(home, target, use_environment=False, force=False):
    """Generate from installed binaries only; preserve edits and cache by version.

    Returns per-tool/shell status. Unsupported optional generators do not prevent
    activation of the shell or discard an existing completion file.
    """
    _, ledger = config_targets(home, target, use_environment)
    directory = ledger.parent / "completions"
    cache = directory / "manifest.json"
    reject_links(cache)
    report = []
    with configuration_lock(ledger.parent):
        previous = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        if not isinstance(previous, dict):
            raise ValueError("Invalid completion manifest: " + str(cache))
        state = dict(previous)
        for tool, command in COMPLETION_COMMANDS.items():
            binary = shutil.which(tool)
            if not binary:
                report.append({"tool": tool, "status": "missing"})
                continue
            try:
                version = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True, timeout=15).stdout.strip()
            except (OSError, subprocess.SubprocessError) as error:
                report.append({"tool": tool, "status": "unavailable", "detail": str(error)})
                continue
            identity = {"binary": str(Path(binary).resolve()), "version": version}
            for shell in (["powershell"] if target == "windows" else ["bash", "zsh"]):
                args = command(shell)
                if args is None:
                    report.append({"tool": tool, "shell": shell, "status": "unsupported"})
                    continue
                filename = "_" + tool if shell == "zsh" else tool + (".ps1" if shell == "powershell" else ".bash")
                destination = directory / shell / filename
                reject_links(destination)
                key = shell + "/" + filename
                old = state.get(key)
                if old is not None and (not isinstance(old, dict) or not isinstance(old.get("hash"), str)):
                    raise ValueError("Invalid completion record: " + key)
                current = destination.read_bytes() if destination.exists() else None
                if current is not None and (not old or old["hash"] != digest(current)):
                    report.append({"tool": tool, "shell": shell, "status": "preserved"})
                    continue
                if not force and current is not None and old and all(old.get(k) == v for k, v in identity.items()):
                    report.append({"tool": tool, "shell": shell, "status": "cached"})
                    continue
                try:
                    output = subprocess.run([binary, *args], capture_output=True, check=True, timeout=30).stdout
                    if not output.strip():
                        raise ValueError("Empty completion output")
                    if current != output:
                        atomic_write(destination, output)
                    state[key] = dict(identity, hash=digest(output))
                    report.append({"tool": tool, "shell": shell, "status": "generated"})
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    report.append({"tool": tool, "shell": shell, "status": "unavailable", "detail": str(error)})
        desired = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
        if not cache.exists() or cache.read_bytes() != desired:
            atomic_write(cache, desired)
    return report
