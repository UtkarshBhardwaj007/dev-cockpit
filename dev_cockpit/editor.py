"""Safe editor command construction and foreground execution.

The editor bridge deliberately keeps paths as argv elements.  Persistent Fresh
routing is not implemented here until its literal-path and acknowledgement
contracts have been qualified against the packaged version.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Iterable, Mapping, Optional, Sequence, Tuple


SETTINGS_SCHEMA = 1
BACKENDS = ("fresh", "external")
PACK_ORDER = ("go", "python", "java", "typescript", "cpp", "csharp", "rust", "bash")
PACK_ALIASES = {"javascript": "typescript", "js": "typescript", "ts": "typescript"}
LANGUAGE_PACKS = {
    "go": {"languages": ("Go",), "tools": ("gopls",)},
    "python": {"languages": ("Python",), "tools": ("pylsp",)},
    "java": {"languages": ("Java",), "tools": ("jdtls",)},
    "typescript": {
        "languages": ("JavaScript", "TypeScript"),
        "tools": ("typescript-language-server",),
    },
    "cpp": {"languages": ("C++",), "tools": ("clangd", "clang-format")},
    "csharp": {"languages": ("C#",), "tools": ("csharp-ls",)},
    "rust": {"languages": ("Rust",), "tools": ("rust-analyzer", "rustfmt")},
    "bash": {
        "languages": ("Bash",),
        "tools": ("bash-language-server", "shellcheck", "shfmt"),
    },
}
_SETTING_KEYS = {
    "schema", "backend", "external_command", "external_wait_command", "language_packs"
}


class EditorError(ValueError):
    """An editor request cannot be completed without changing its meaning."""


class RoutingUnavailable(EditorError):
    """The selected editor has no qualified persistent routing implementation."""


@dataclass(frozen=True)
class EditorSettings:
    schema: int = SETTINGS_SCHEMA
    backend: str = "fresh"
    external_command: Optional[Tuple[str, ...]] = None
    external_wait_command: Optional[Tuple[str, ...]] = None
    language_packs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EditorCommand:
    argv: Tuple[str, ...]
    environment: Mapping[str, str]


@dataclass(frozen=True)
class EditorRequest:
    settings: EditorSettings
    project: Path
    files: Tuple[Path, ...] = ()
    line: Optional[int] = None
    column: Optional[int] = None
    standalone: bool = False
    wait: bool = False
    herdr_session: Optional[str] = None
    environment: Optional[Mapping[str, str]] = None


def _absolute_environment_path(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise EditorError(label + " must be absolute: " + str(path))
    return path


def editor_settings_path(home, target: str, environment: Optional[Mapping[str, str]] = None) -> Path:
    """Return the user-owned editor settings path for a selected user home.

    Environment-derived paths are used only when the caller explicitly passes
    an environment.  This prevents installer service-account variables from
    silently overriding the selected interactive user's home.
    """
    home = Path(home).resolve()
    env = environment or {}
    if target == "windows":
        root = home / "AppData/Roaming"
        if env.get("APPDATA"):
            root = _absolute_environment_path(env["APPDATA"], "APPDATA")
    elif target in ("macos", "linux"):
        root = home / ".config"
        if env.get("XDG_CONFIG_HOME"):
            root = _absolute_environment_path(env["XDG_CONFIG_HOME"], "XDG_CONFIG_HOME")
    else:
        raise EditorError("Unsupported editor platform: " + target)
    return root / "dev-cockpit/editor.json"


def _editor_settings_candidates(home, target: str,
                                environment: Optional[Mapping[str, str]]) -> Tuple[Path, ...]:
    selected = editor_settings_path(home, target, environment)
    fallback = editor_settings_path(home, target, None)
    return (selected,) if selected == fallback else (selected, fallback)


def _command(value, name: str) -> Optional[Tuple[str, ...]]:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise EditorError(name + " must be null or a nonempty JSON argv array")
    for item in value:
        if not isinstance(item, str) or not item.strip() or "\0" in item:
            raise EditorError(name + " must contain only nonempty strings")
    return tuple(value)


def canonical_language_packs(values: Iterable[str], *, allow_all: bool = True) -> Tuple[str, ...]:
    """Validate pack IDs, expanding ``all`` and JavaScript aliases once."""
    if isinstance(values, (str, bytes)):
        raise EditorError("language_packs must be an array of pack IDs")
    selected = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise EditorError("language_packs must contain nonempty strings")
        pack = value.lower()
        if pack == "all":
            if not allow_all:
                raise EditorError("'all' is an install selection, not a stored language pack")
            candidates = PACK_ORDER
        else:
            pack = PACK_ALIASES.get(pack, pack)
            if pack not in LANGUAGE_PACKS:
                raise EditorError("Unknown language pack: " + value)
            candidates = (pack,)
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
    return tuple(selected)


def validate_editor_settings(value) -> EditorSettings:
    if not isinstance(value, dict):
        raise EditorError("Editor settings must be a JSON object")
    unknown = sorted(set(value) - _SETTING_KEYS)
    if unknown:
        raise EditorError("Unknown editor setting(s): " + ", ".join(unknown))
    if type(value.get("schema")) is not int or value["schema"] != SETTINGS_SCHEMA:
        raise EditorError("Unsupported editor settings schema; expected 1")
    backend = value.get("backend")
    if backend not in BACKENDS:
        raise EditorError("backend must be 'fresh' or 'external'")
    external = _command(value.get("external_command"), "external_command")
    external_wait = _command(value.get("external_wait_command"), "external_wait_command")
    packs = value.get("language_packs")
    if not isinstance(packs, list):
        raise EditorError("language_packs must be a JSON array")
    packs = canonical_language_packs(packs, allow_all=False)
    if backend == "external" and external is None:
        raise EditorError("external backend requires external_command")
    return EditorSettings(SETTINGS_SCHEMA, backend, external, external_wait, packs)


def resolve_editor_settings(home, target: str, environment: Optional[Mapping[str, str]] = None) -> EditorSettings:
    """Load editor.json, or return the conservative Fresh defaults when absent."""
    candidates = _editor_settings_candidates(home, target, environment)
    for index, path in enumerate(candidates):
        try:
            raw = path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError):
            continue
        except UnicodeError as error:
            raise EditorError("Invalid UTF-8 in editor settings " + str(path) + ": " + str(error)) from error
        except OSError as error:
            # Environment-derived Windows locations can belong to an installer
            # or service profile.  Treat an inaccessible discovery candidate as
            # absent, while still surfacing a failure at the selected-home path.
            if index + 1 < len(candidates):
                continue
            raise EditorError("Could not read editor settings " + str(path) + ": " + str(error)) from error
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise EditorError("Invalid JSON in editor settings " + str(path) + ": " + str(error)) from error
        return validate_editor_settings(value)
    return EditorSettings()


FRESH_QUALIFIED_TARGETS = ("macos",)


def fresh_qualified(target: str) -> bool:
    """Report whether this platform is a qualified Fresh release target.

    macOS is the mandatory target. Linux and Windows keep the portable bridge
    and configuration plumbing, but their editor integration is experimental
    until it is qualified, so callers must not assume Fresh is usable there.
    """
    return target in FRESH_QUALIFIED_TARGETS


def code_layout_support(target: str, *, settings: Optional[EditorSettings] = None,
                        finder: Callable[[str], Optional[str]] = shutil.which) -> Tuple[bool, str]:
    """Report whether the editor-centric Herdr layout can run here.

    An unavailable editor must never be placed into a pane: a failed pane
    command would leave the user with a broken workspace instead of the classic
    one.  Callers explain the reason and keep the existing layout.  The check is
    intentionally about the *managed Fresh* pane, so a configured external
    backend is reported rather than silently replaced by Fresh.
    """
    if not fresh_qualified(target):
        return False, ("The code layout uses Fresh, whose integration is experimental on this "
                       "platform. The classic layout (dev open .) keeps OMP, Yazi and the shell.")
    if settings is not None and settings.backend != "fresh":
        return False, ("The code layout hosts the managed Fresh pane, but editor.json selects the "
                       "external backend. The classic layout keeps your existing editor; set "
                       "\"backend\": \"fresh\" to use the editor pane.")
    if _find_executable(("fresh",), finder) is None:
        return False, ("The code layout needs the Fresh editor, which is not on PATH. Rerun setup "
                       "to install it, or use the classic layout (dev open .).")
    return True, ""


def _existing_editor_command(environment: Optional[Mapping[str, str]]) -> Optional[Tuple[str, ...]]:
    """Return the user's configured external editor as one argv token.

    ``$VISUAL``/``$EDITOR`` are treated as a single executable, never word
    split: a bare path containing spaces must keep working, and a value such as
    ``code --wait`` is documented as requiring the argv form in editor.json.
    """
    env = environment or {}
    for name in ("VISUAL", "EDITOR"):
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return (value.strip(),)
    return None


def effective_editor_settings(settings: EditorSettings, *, target: str,
                              environment: Optional[Mapping[str, str]] = None,
                              finder: Callable[[str], Optional[str]] = shutil.which) -> EditorSettings:
    """Return settings that can actually run on this machine.

    Fresh remains the managed default. When the Fresh binary is absent, the
    user's existing ``$VISUAL``/``$EDITOR`` is used so ``dev edit`` and ``fe``
    keep working instead of failing outright. This is never silent: callers
    report the substitution with :func:`describe_editor_substitution`, and a
    missing fallback is an explicit error naming the repair options rather than
    a confusing "no such file" from the process launcher.
    """
    if not isinstance(settings, EditorSettings):
        raise EditorError("settings must be validated EditorSettings")
    if settings.backend != "fresh":
        return settings
    if _find_executable(("fresh",), finder) is not None:
        return settings
    fallback = _existing_editor_command(environment)
    if fallback is None:
        raise EditorError(
            "Fresh is not installed and no VISUAL/EDITOR editor is configured. "
            "Rerun setup to install Fresh, or set an external editor command in editor.json."
        )
    return EditorSettings(SETTINGS_SCHEMA, "external", fallback, fallback, settings.language_packs)


def describe_editor_substitution(settings: EditorSettings, effective: EditorSettings,
                                 target: str) -> Optional[str]:
    """Explain a Fresh-to-external substitution, or return None when none happened."""
    if settings.backend == effective.backend:
        return None
    status = "experimental" if not fresh_qualified(target) else "not installed"
    return ("Fresh is " + status + " on this platform; using the configured "
            + "VISUAL/EDITOR (" + str(effective.external_command[0]) + ") instead.")


def canonical_project(project) -> Path:
    try:
        path = Path(project).expanduser().resolve()
        directory = path.is_dir()
    except OSError as error:
        raise EditorError("Project directory is not accessible: " + str(project)) from error
    if not directory:
        raise EditorError("Project directory does not exist: " + str(path))
    return path


def _path_kind(path: Path) -> str:
    try:
        if path.is_dir():
            return "directory"
        if path.exists():
            return "file" if path.is_file() else "special"
    except OSError:
        return "inaccessible"
    return "missing"


def normalize_edit_paths(paths: Sequence, *, project=None, cwd=None) -> Tuple[Path, Tuple[Path, ...]]:
    """Canonicalize literal path arguments and select the editor project.

    A sole directory selects the project.  Existing files must be readable; a
    new file is accepted only when its parent directory exists and is writable.
    """
    base = canonical_project(cwd or Path.cwd())
    requested = []
    for original in paths:
        path = Path(original).expanduser()
        if not path.is_absolute():
            path = base / path
        try:
            requested.append(path.resolve(strict=False))
        except OSError as error:
            raise EditorError("Path is not accessible: " + str(path)) from error
    kinds = [_path_kind(path) for path in requested]
    directories = [path for path, kind in zip(requested, kinds) if kind == "directory"]
    if directories:
        if len(requested) != 1:
            raise EditorError("A directory may be opened only as the sole path; do not mix directories and files")
        if project is not None and canonical_project(project) != directories[0]:
            raise EditorError("The directory path conflicts with --project")
        return directories[0], ()
    selected_project = canonical_project(project if project is not None else base)
    for path, kind in zip(requested, kinds):
        if kind in ("special", "inaccessible"):
            raise EditorError("File path is not accessible: " + str(path))
        if kind == "file":
            try:
                readable = os.access(str(path), os.R_OK)
            except OSError:
                readable = False
            if not readable:
                raise EditorError("File is not readable: " + str(path))
        elif kind == "missing":
            parent = path.parent
            try:
                usable = parent.is_dir() and os.access(str(parent), os.W_OK | os.X_OK)
            except OSError:
                usable = False
            if not usable:
                raise EditorError("New file parent does not exist or is not writable: " + str(parent))
    return selected_project, tuple(requested)


def validate_location(files: Sequence, line=None, column=None) -> Optional[Tuple[Optional[int], Optional[int]]]:
    if line is None and column is None:
        return None
    if len(files) != 1:
        raise EditorError("--line and --column require exactly one file")
    for value, name in ((line, "line"), (column, "column")):
        if value is not None and (type(value) is not int or value <= 0):
            raise EditorError("--" + name + " must be a positive integer")
    if column is not None and line is None:
        raise EditorError("--column requires --line")
    return line, column


def project_identity(project, herdr_session: str) -> str:
    """Return a stable identity that keeps sibling worktrees separate."""
    if not isinstance(herdr_session, str) or not herdr_session:
        raise EditorError("Herdr session must be a nonempty string")
    canonical = str(canonical_project(project))
    material = herdr_session + "\0" + os.path.normcase(canonical)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def build_editor_command(settings: EditorSettings, files: Sequence, location=None,
                         mode: str = "foreground", *, project=None,
                         herdr_session: Optional[str] = None,
                         environment: Optional[Mapping[str, str]] = None) -> EditorCommand:
    """Build an argv-only editor invocation and its explicit child context."""
    if not isinstance(settings, EditorSettings):
        raise EditorError("settings must be validated EditorSettings")
    if mode not in ("foreground", "standalone", "wait", "persistent"):
        raise EditorError("Unknown editor mode: " + mode)
    files = tuple(Path(path) for path in files)
    normalized_location = None
    if location is not None:
        try:
            line, column = location
        except (TypeError, ValueError) as error:
            raise EditorError("location must be a (line, column) pair") from error
        normalized_location = validate_location(files, line, column)
    if mode == "persistent":
        raise RoutingUnavailable("Persistent editor routing has not been qualified for the packaged Fresh release")
    if settings.backend == "fresh":
        prefix = ("fresh",)
    elif mode == "wait":
        if settings.external_wait_command is None:
            raise EditorError("External editor waiting requires external_wait_command")
        prefix = settings.external_wait_command
    else:
        prefix = settings.external_command
    if not prefix:
        raise EditorError("The selected editor command is not configured")
    arguments = tuple(str(path) for path in files)
    if normalized_location is not None:
        if settings.backend != "fresh":
            raise RoutingUnavailable("Exact locations are not defined for the configured external editor")
        path = arguments[0]
        if ":" in path:
            # Fresh 0.5.1 accepts path:line:column but offers no qualified
            # structured/literal alternative.  Colons are legal in Unix names
            # and unavoidable in Windows drive paths, so those must not be
            # rewritten into an ambiguous argument.
            raise RoutingUnavailable("Exact Fresh locations are ambiguous for paths containing ':'")
        line, column = normalized_location
        path += ":" + str(line)
        if column is not None:
            path += ":" + str(column)
        arguments = (path,)
    env = dict(os.environ if environment is None else environment)
    if project is not None:
        canonical = canonical_project(project)
        env["DEV_COCKPIT_PROJECT"] = str(canonical)
        if herdr_session:
            env["DEV_COCKPIT_HERDR_SESSION"] = herdr_session
            env["DEV_COCKPIT_EDITOR_KEY"] = project_identity(canonical, herdr_session)
    return EditorCommand(tuple(prefix) + arguments, env)


def build_editor_pane_command(settings: EditorSettings, project, herdr_session: str,
                              environment: Optional[Mapping[str, str]] = None) -> EditorCommand:
    """Build the verified Fresh named-session command for a Herdr editor pane."""
    if not isinstance(settings, EditorSettings):
        raise EditorError("settings must be validated EditorSettings")
    if settings.backend != "fresh":
        raise EditorError("An external editor cannot be hosted in a Herdr terminal pane")
    canonical = canonical_project(project)
    key = project_identity(canonical, herdr_session)
    env = dict(os.environ if environment is None else environment)
    env.update({
        "DEV_COCKPIT_PROJECT": str(canonical),
        "DEV_COCKPIT_HERDR_SESSION": herdr_session,
        "DEV_COCKPIT_EDITOR_KEY": key,
    })
    return EditorCommand(("fresh", "-a", key), env)


def open_files(request: EditorRequest, *, runner: Callable = subprocess.run) -> int:
    """Run a foreground editor and return its exit code.

    Foreground execution is also the honest fallback inside a cockpit until the
    persistent Fresh route is qualified.  It naturally supplies wait semantics
    for Fresh; external editors use their separately configured wait command.
    """
    if not isinstance(request, EditorRequest):
        raise EditorError("request must be an EditorRequest")
    project, files = normalize_edit_paths(
        request.files, project=request.project, cwd=request.project)
    location = validate_location(files, request.line, request.column)
    mode = "wait" if request.wait else ("standalone" if request.standalone else "foreground")
    command = build_editor_command(
        request.settings, files, location, mode, project=project,
        herdr_session=request.herdr_session, environment=request.environment,
    )
    result = runner(list(command.argv), cwd=str(project), env=dict(command.environment), shell=False)
    return int(result.returncode)


def language_pack_status(settings: EditorSettings, finder: Callable[[str], Optional[str]] = shutil.which):
    """Describe every pack without installing or modifying anything."""
    configured = set(settings.language_packs)
    result = []
    for pack in PACK_ORDER:
        tools = []
        for executable in LANGUAGE_PACKS[pack]["tools"]:
            try:
                found = finder(executable)
            except OSError:
                found = None
            tools.append({"name": executable, "path": found, "status": "found" if found else "missing"})
        result.append({
            "id": pack,
            "languages": list(LANGUAGE_PACKS[pack]["languages"]),
            "configured": pack in configured,
            "status": "ready" if all(tool["path"] for tool in tools) else "missing",
            "tools": tools,
        })
    return result


def _find_executable(command: Sequence[str], finder: Callable[[str], Optional[str]]) -> Optional[str]:
    name = command[0]
    try:
        if os.path.dirname(name):
            path = Path(name)
            return str(path) if path.is_file() and os.access(str(path), os.X_OK) else None
        return finder(name)
    except OSError:
        return None


def doctor_editor(settings: EditorSettings, *, home=None, target=None, project=None,
                  herdr_session=None, environment=None, finder=shutil.which,
                  runner=subprocess.run):
    """Return structured, read-only editor and language health checks."""
    selected = settings.external_command if settings.backend == "external" else ("fresh",)
    binary = _find_executable(selected, finder)
    version = None
    detail = None
    if binary:
        try:
            checked = runner([binary, "--version"], capture_output=True, text=True,
                             timeout=10, shell=False, env=dict(os.environ if environment is None else environment))
            output = (checked.stdout or checked.stderr).strip()
            if checked.returncode == 0:
                version = output.splitlines()[0] if output else "unknown"
            else:
                detail = output or "version command exited " + str(checked.returncode)
        except (OSError, subprocess.SubprocessError) as error:
            detail = str(error)
    result = {
        "status": "ready" if binary else "missing",
        "backend": settings.backend,
        "binary": binary,
        "version": version,
        "detail": detail,
        "routing": "foreground",
        "languages": language_pack_status(settings, finder),
    }
    if home is not None and target is not None:
        result["settings_path"] = str(editor_settings_path(home, target, environment))
    if project is not None:
        canonical = canonical_project(project)
        result["project"] = str(canonical)
        if herdr_session:
            result["editor_key"] = project_identity(canonical, herdr_session)
            result["herdr_session"] = herdr_session
    return result
