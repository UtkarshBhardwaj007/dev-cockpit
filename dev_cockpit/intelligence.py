"""Project-scoped OMP memory and local Graphify integration.

No model requests occur here. OMP's separately launched local-summary backend
uses the user's configured model provider; local storage is not offline inference.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
GRAPHIFY_PACKAGE = "graphifyy[mcp]==0.9.57"
GRAPHIFY_PYTHON = "3.12"
SERVER_NAME = "dev-cockpit-graphify"
LOCAL = Path(".dev-cockpit/intelligence")
MEMORY_OVERLAY = LOCAL / "memory.yml"
MEMORY_RULE = Path(".omp/rules/dev-cockpit-memory.md")
GRAPH_SKILL = Path(".omp/skills/dev-cockpit-graphify/SKILL.md")
MCP_FILE = Path(".omp/mcp.json")
GRAPH = LOCAL / "graph/graphify-out/graph.json"
STATE = LOCAL / "state.json"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _reject_links(path):
    for entry in (path, *path.parents):
        if entry.is_symlink() or (entry.exists() and bool(
                getattr(entry.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))):
            raise ValueError("Refusing symlink/junction in managed path: " + str(entry))


def _write(path, data):
    _reject_links(path)
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


def _json(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _read_object(path):
    _reject_links(path)
    value = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return value


def _project(project):
    result = Path(project).expanduser().resolve()
    if not result.is_dir():
        raise ValueError("Project directory does not exist: " + str(result))
    if result == Path.home().resolve() or result.parent == result:
        raise ValueError("Select a project directory, not your home or filesystem root")
    return result


@contextmanager
def _locked(project):
    """Serialize project writes; a leftover lock needs explicit user inspection."""
    root = project / LOCAL
    _reject_links(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".lock"
    _reject_links(lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError("Intelligence operation already running; inspect " + str(lock)) from error
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _state(project):
    state = _read_object(project / STATE)
    if not isinstance(state.get("files", {}), dict):
        raise ValueError("Invalid intelligence ownership ledger")
    state.setdefault("files", {})
    return state


def _save(project, state):
    _write(project / STATE, _json(state))


def _manage(project, state, relative, desired=None):
    """Manage only declared files, never paths supplied by the ownership ledger."""
    path = project / relative
    _reject_links(path)
    current = path.read_bytes() if path.exists() else None
    owned = current is not None and state["files"].get(str(relative)) == _digest(current)
    if desired is None:
        if owned:
            path.unlink()
            state["files"].pop(str(relative), None)
        elif current is not None:
            print("PRESERVE user-edited file:", path)
        return owned
    if current is not None and not owned:
        print("PRESERVE existing/user-edited file:", path)
        return False
    if current != desired:
        _write(path, desired)
    state["files"][str(relative)] = _digest(desired)
    # Persist after each write; interrupted operations never assume ownership.
    _save(project, state)
    return True


def graph_bin(home=None):
    """Stable isolated uv tool bin directory (also used on native Windows)."""
    return Path(home or Path.home()).expanduser().resolve() / ".local/share/dev-cockpit/graphify/bin"


def _graph_tools(home=None):
    suffix = ".exe" if os.name == "nt" else ""
    result = []
    for name in ("graphify", "graphify-mcp"):
        private = graph_bin(home) / (name + suffix)
        result.append(str(private) if private.is_file() else shutil.which(name))
    return tuple(result)


def _check_tools(tools):
    cli, server = tools
    if not cli or not server:
        return False
    try:
        command = subprocess.run([cli, "--help"], check=True, capture_output=True, text=True, timeout=30)
        subprocess.run([server, "--help"], check=True, capture_output=True, timeout=30)
        if "--code-only" not in command.stdout or "extract" not in command.stdout:
            return False
        # Both entrypoints also ship with graphifyy without the optional MCP
        # dependency. --help alone succeeds in that broken-for-us installation.
        with tempfile.TemporaryDirectory(prefix="cockpit-mcp-check-") as temporary:
            graph = Path(temporary) / "graph.json"
            graph.write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
            mcp_probe(server, graph, timeout=15)
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def install_graphify(home=None, upgrade=False):
    """Install only missing tools, or explicitly update a private managed install."""
    tools = _graph_tools(home)
    if not upgrade and _check_tools(tools):
        print("PRESENT Graphify CLI and MCP; no download or reinstall")
        return tools
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv is missing. Run dev setup with the intelligence profile first.")
    base = graph_bin(home).parent
    _reject_links(base)
    env = os.environ.copy()
    env.update({"UV_TOOL_DIR": str(base / "tools"), "UV_TOOL_BIN_DIR": str(base / "bin"),
                "UV_PYTHON_INSTALL_DIR": str(base / "python")})
    command = [uv, "tool", "install", "--python", GRAPHIFY_PYTHON, GRAPHIFY_PACKAGE]
    if upgrade:
        command += ["--upgrade", "--reinstall"]
    subprocess.run(command, check=True, env=env)
    tools = _graph_tools(home)
    if not _check_tools(tools):
        raise ValueError("Graphify installation did not provide a usable CLI and MCP server")
    print("READY", GRAPHIFY_PACKAGE, "in", base)
    return tools


def _require_graphify(home=None):
    tools = _graph_tools(home)
    if not _check_tools(tools):
        raise ValueError("Graphify CLI/MCP unavailable or incompatible. Run: dev graph install")
    return tools


def _mcp_document(project):
    config = _read_object(project / MCP_FILE)
    if not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("mcpServers must be an object in " + str(project / MCP_FILE))
    return config


def _register_mcp(project, state, command, remove=False):
    config = _mcp_document(project)
    servers = config.setdefault("mcpServers", {})
    previous = servers.get(SERVER_NAME)
    recorded = state.get("mcp_entry")
    if previous is not None and previous != recorded:
        if remove:
            print("PRESERVE user-edited MCP entry:", SERVER_NAME)
            return
        raise ValueError("MCP entry already exists or was edited: " + SERVER_NAME)
    if remove:
        if previous is not None:
            servers.pop(SERVER_NAME)
            _write(project / MCP_FILE, _json(config))
        state.pop("mcp_entry", None)
    else:
        desired = {"type": "stdio", "command": command,
                   "args": [str(project / GRAPH)], "cwd": str(project), "timeout": 30000}
        if previous != desired:
            servers[SERVER_NAME] = desired
            _write(project / MCP_FILE, _json(config))
        state["mcp_entry"] = desired
    _save(project, state)


def _source_fingerprint(project):
    """Content-based freshness, including new/deleted files; never follows links."""
    skip = {".git", ".dev-cockpit", ".omp", ".venv", "venv", "node_modules", "__pycache__",
            "graphify-out", "target", "dist", "build", ".next", ".idea", ".vscode"}
    result = hashlib.sha256()
    for directory, dirs, files in os.walk(project, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in skip and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            result.update(path.relative_to(project).as_posix().encode("utf-8"))
            result.update(b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    result.update(chunk)
    return result.hexdigest()


def _validate_graph(path):
    graph = _read_object(path)
    if not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges", graph.get("links")), list):
        raise ValueError("Graphify did not produce a valid graph: " + str(path))
    return graph


def graph_update(project, home=None, force=False):
    project = _project(project)
    cli, _ = _require_graphify(home)
    with _locked(project):
        state = _state(project)
        output = project / GRAPH
        fingerprint = _source_fingerprint(project)
        if not force and output.exists() and state.get("source_fingerprint") == fingerprint:
            _validate_graph(output)
            print("UNCHANGED source files; reuse", output)
            return output
        graph_root = project / LOCAL / "graph"
        _reject_links(graph_root)
        if graph_root.exists():
            for path in graph_root.rglob("*"):
                _reject_links(path)
        backup = output.read_bytes() if output.exists() else None
        command = [cli, "extract", str(project), "--code-only", "--no-cluster",
                   "--out", str(graph_root), "--exclude", ".dev-cockpit", "--exclude", ".omp",
                   "--max-workers", "2"]
        if force:
            command.append("--force")
        try:
            subprocess.run(command, cwd=project, check=True)
            graph = _validate_graph(output)
        except (OSError, ValueError, subprocess.SubprocessError):
            if backup is not None:
                _write(output, backup)
            elif output.exists():
                output.unlink()
            raise
        state["source_fingerprint"] = fingerprint
        state["indexed_at"] = datetime.now(timezone.utc).isoformat()
        state["graph_nodes"] = len(graph["nodes"])
        _save(project, state)
        print("INDEXED", len(graph["nodes"]), "nodes with local AST extraction:", output)
        return output


def graph_init(project, home=None):
    project = _project(project)
    _, server = _require_graphify(home)
    # Conflicts are detected before indexing or rewriting any agent config.
    config = _mcp_document(project)
    previous = config.get("mcpServers", {}).get(SERVER_NAME)
    if previous is not None and previous != _state(project).get("mcp_entry"):
        raise ValueError("MCP entry already exists or was edited: " + SERVER_NAME)
    graph_update(project, home)
    with _locked(project):
        state = _state(project)
        _manage(project, state, LOCAL / ".gitignore", b"*\n")
        _manage(project, state, GRAPH_SKILL, (ROOT / "config/intelligence/graphify-SKILL.md").read_bytes())
        _register_mcp(project, state, server)
        state["graph_enabled"] = True
        _save(project, state)
    print("Graphify ready in OMP; restart the session, then run /mcp and /skill:dev-cockpit-graphify")


def graph_disable(project):
    project = _project(project)
    with _locked(project):
        state = _state(project)
        _register_mcp(project, state, None, remove=True)
        _manage(project, state, GRAPH_SKILL)
        state["graph_enabled"] = False
        _save(project, state)
    print("Disabled managed Graphify integration; saved graph retained:", project / GRAPH)


def memory_enable(project):
    project = _project(project)
    with _locked(project):
        state = _state(project)
        _manage(project, state, LOCAL / ".gitignore", b"*\n")
        ready = _manage(project, state, MEMORY_OVERLAY, (ROOT / "config/intelligence/memory.yml").read_bytes())
        _manage(project, state, MEMORY_RULE, (ROOT / "config/intelligence/memory-rule.md").read_bytes())
        if not ready:
            raise ValueError("Memory overlay was preserved; inspect " + str(project / MEMORY_OVERLAY))
        state["memory_enabled"] = True
        _save(project, state)
    print("Enabled project memory. Launch via dev open; OMP summaries use your configured model provider.")


def memory_disable(project):
    project = _project(project)
    with _locked(project):
        state = _state(project)
        _manage(project, state, MEMORY_OVERLAY)
        _manage(project, state, MEMORY_RULE)
        state["memory_enabled"] = False
        _save(project, state)
    print("Disabled cockpit memory overlay; saved notes and OMP memory retained. Existing OMP settings still apply.")


def omp_command(project, executable="omp"):
    project = _project(project)
    state = _state(project)
    command = [str(executable)]
    if state.get("memory_enabled"):
        overlay = project / MEMORY_OVERLAY
        _reject_links(overlay)
        if not overlay.is_file():
            raise ValueError("Enabled memory overlay is missing; run dev memory enable for this project")
        command += ["--config", str(overlay)]
    return command


def memory_remember(project, text):
    """Explicit user notes are useful immediately, without any model or account."""
    project = _project(project)
    if not text.strip() or len(text) > 8000:
        raise ValueError("Memory note must contain 1 to 8000 characters")
    with _locked(project):
        state = _state(project)
        _manage(project, state, LOCAL / ".gitignore", b"*\n")
        path = project / LOCAL / "notes.json"
        notes = _read_object(path)
        entries = notes.setdefault("entries", [])
        if not isinstance(entries, list):
            raise ValueError("Invalid memory notes")
        if not any(entry.get("text") == text.strip() for entry in entries):
            entries.append({"id": uuid.uuid4().hex[:12], "text": text.strip(),
                            "created_at": datetime.now(timezone.utc).isoformat()})
            _write(path, _json(notes))
        print("Saved project note:", path)


def memory_show(project):
    project = _project(project)
    entries = _read_object(project / LOCAL / "notes.json").get("entries", [])
    for entry in entries:
        print(entry["id"] + ": " + entry["text"])
    if not entries:
        print("No manual notes yet. Native OMP summaries are visible through /memory view in OMP.")
    return entries


def mcp_probe(command, graph, timeout=30, question=None):
    """Exercise a real stdio MCP handshake, list, and graph_stats call."""
    messages = queue.Queue()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([command, str(graph)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors, text=True, encoding="utf-8", bufsize=1)
        def read_lines():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    pass
            messages.put(None)
        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()
        def send(method, params, identifier=None):
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if identifier is not None:
                message["id"] = identifier
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            if identifier is None:
                return None
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("MCP request timed out: " + method)
                try:
                    response = messages.get(timeout=remaining)
                except queue.Empty as error:
                    raise ValueError("MCP request timed out: " + method) from error
                if response is None:
                    errors.seek(0)
                    detail = errors.read().decode("utf-8", errors="replace")[-1500:]
                    raise ValueError("MCP server exited before responding: " + detail)
                if response.get("id") == identifier:
                    if "error" in response:
                        raise ValueError("MCP error: " + json.dumps(response["error"]))
                    return response["result"]
        try:
            initialized = send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "dev-cockpit-doctor", "version": "1"}}, 1)
            send("notifications/initialized", {})
            tool_result = send("tools/list", {}, 2)
            names = [entry["name"] for entry in tool_result["tools"]]
            if "graph_stats" not in names or "query_graph" not in names:
                raise ValueError("Graphify MCP is missing expected graph tools")
            stats = send("tools/call", {"name": "graph_stats", "arguments": {}}, 3)
            if stats.get("isError"):
                raise ValueError("Graphify graph_stats returned an error")
            result = {"server": initialized.get("serverInfo"), "tools": names, "stats": stats}
            if question is not None:
                result["query"] = send("tools/call", {"name": "query_graph", "arguments": {"question": question}}, 4)
                if result["query"].get("isError"):
                    raise ValueError("Graphify query_graph returned an error")
            return result
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            reader.join(timeout=1)
            process.stdout.close()


def doctor(project, kind="graph", home=None, live=False):
    project = _project(project)
    state = _state(project)
    failures = []
    if kind == "memory":
        enabled = bool(state.get("memory_enabled"))
        print("MEMORY", "enabled" if enabled else "disabled", "for", project)
        if enabled and not (project / MEMORY_OVERLAY).is_file():
            failures.append("Memory overlay is missing")
        print("Manual notes:", len(_read_object(project / LOCAL / "notes.json").get("entries", [])))
        print("Native consolidation requires a persisted OMP session and a configured model. Use /memory diagnose in OMP.")
    else:
        cli, server = _graph_tools(home)
        if not _check_tools((cli, server)):
            failures.append("Graphify CLI or MCP missing; run dev graph install")
        path = project / GRAPH
        if not path.exists():
            failures.append("No graph; run dev graph init for this project")
        else:
            graph = _validate_graph(path)
            print("GRAPH", len(graph["nodes"]), "nodes", path)
            if state.get("source_fingerprint") != _source_fingerprint(project):
                failures.append("Graph is stale; run dev graph update for this project")
            if live and server:
                probe = mcp_probe(server, path)
                print("MCP handshake, tools/list, graph_stats PASS:", ", ".join(probe["tools"]))
        config = _mcp_document(project)
        entry = config.get("mcpServers", {}).get(SERVER_NAME)
        if not entry or entry != state.get("mcp_entry"):
            failures.append("Managed OMP MCP registration missing or changed")
        if SERVER_NAME in config.get("disabledServers", []) or (entry and entry.get("enabled") is False):
            failures.append("Graphify MCP is disabled in the project configuration")
    for failure in failures:
        print("ATTENTION", failure)
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    kinds = parser.add_subparsers(dest="kind", required=True)
    graph = kinds.add_parser("graph")
    graph.add_argument("action", choices=["install", "init", "update", "doctor", "disable"])
    graph.add_argument("project", nargs="?", default=".")
    graph.add_argument("--home", type=Path, help="Isolated Graphify installation root")
    graph.add_argument("--upgrade", action="store_true", help="Explicitly reinstall the pinned private Graphify tool")
    graph.add_argument("--force", action="store_true", help="Force graph reindex (never downloads packages)")
    graph.add_argument("--live", action="store_true", help="Doctor: exercise real MCP handshake and graph_stats")
    memory = kinds.add_parser("memory")
    memory.add_argument("action", choices=["enable", "disable", "doctor", "remember", "show"])
    memory.add_argument("project", nargs="?", default=".")
    memory.add_argument("--text", help="Explicit project note for remember; never store credentials")
    args = parser.parse_args(argv)
    try:
        if args.kind == "graph":
            if args.upgrade and args.action != "install":
                parser.error("--upgrade only applies to graph install")
            if args.force and args.action != "update":
                parser.error("--force only applies to graph update")
            if args.live and args.action != "doctor":
                parser.error("--live only applies to graph doctor")
            if args.action == "install":
                install_graphify(args.home, args.upgrade)
            elif args.action == "init":
                graph_init(args.project, args.home)
            elif args.action == "update":
                graph_update(args.project, args.home, args.force)
            elif args.action == "disable":
                graph_disable(args.project)
            else:
                return doctor(args.project, "graph", args.home, args.live)
        elif args.action == "enable":
            memory_enable(args.project)
        elif args.action == "disable":
            memory_disable(args.project)
        elif args.action == "remember":
            if not args.text:
                parser.error("memory remember requires --text")
            memory_remember(args.project, args.text)
        elif args.action == "show":
            memory_show(args.project)
        else:
            return doctor(args.project, "memory")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("ERROR:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
