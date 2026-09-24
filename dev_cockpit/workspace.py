"""Herdr workspace provisioning via its local API; no shell command interpolation."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import uuid


class HerdrError(RuntimeError):
    pass


class Herdr:
    def __init__(self, executable="herdr", session="dev-cockpit", env=None, timeout=15):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", session):
            raise ValueError("Session names may contain letters, digits, dots, underscores and hyphens.")
        self.executable = executable
        self.session = session
        self.env = dict(os.environ if env is None else env)
        if env is None:
            self.env.pop("HERDR_SOCKET_PATH", None)
        # Never accidentally control the parent pane's different session.
        self.env["HERDR_SESSION"] = session
        for key in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID"):
            self.env.pop(key, None)
        self.timeout = timeout

    def cli(self, *args, json_output=True):
        result = subprocess.run([self.executable, *args], env=self.env, capture_output=True,
                                text=True, encoding="utf-8", timeout=self.timeout)
        if result.returncode:
            raise HerdrError(result.stderr.strip() or result.stdout.strip() or "Herdr command failed")
        if not json_output:
            return result.stdout
        try:
            response = json.loads(result.stdout)
        except ValueError as error:
            raise HerdrError("Invalid JSON returned by Herdr: " + str(error)) from error
        if "error" in response:
            raise HerdrError(str(response["error"]))
        return response.get("result", response)

    def ensure_server(self):
        try:
            self.cli("workspace", "list")
            return False
        except HerdrError as error:
            if "server_not_running" not in str(error):
                raise
        # Explicit headless startup starts only this named session. Existing
        # servers are never restarted, upgraded or stopped by this launcher.
        flags = {}
        if os.name == "nt":
            flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            flags["start_new_session"] = True
        child = subprocess.Popen([self.executable, "server"], env=self.env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, **flags)
        self.started_process = child
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                self.cli("workspace", "list")
                return True
            except HerdrError:
                if child.poll() is not None:
                    raise HerdrError("Herdr server exited during startup; inspect `herdr --session " + self.session + " status server`.")
                time.sleep(0.1)
        raise HerdrError("Timed out starting Herdr. The process was left running for diagnosis.")

    def endpoint(self):
        status = self.cli("status", "server", json_output=False)
        match = re.search(r"^socket:\s*(.+)$", status, re.MULTILINE)
        if not match:
            raise HerdrError("Herdr did not report its local socket/pipe path.")
        return match.group(1).strip()

    def request(self, method, params):
        request_id = "dev-cockpit:" + uuid.uuid4().hex
        payload = (json.dumps({"id": request_id, "method": method, "params": params}) + "\n").encode()
        endpoint = self.endpoint()
        if os.name == "nt":
            response = _pipe_request(endpoint, payload, request_id, self.timeout)
        else:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(endpoint)
                connection.sendall(payload)
                response = _read_response(lambda: connection.recv(65536), request_id)
        if "error" in response:
            raise HerdrError(str(response["error"]))
        return response.get("result", response)

    def attach(self):
        return subprocess.call([self.executable], env=self.env)


def _read_response(read, request_id):
    buffer = b""
    total = 0
    while True:
        data = read()
        if not data:
            raise HerdrError("Herdr closed its local connection before replying.")
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise HerdrError("Herdr response exceeded 8 MiB.")
        buffer += data
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            response = json.loads(line)
            if response.get("id") == request_id:
                return response


def _pipe_request(endpoint, payload, request_id, timeout):
    """Native Windows named pipe transport, bounded reads without extra packages."""
    import ctypes
    from ctypes import wintypes
    import msvcrt
    if not endpoint.startswith("\\\\.\\pipe\\"):
        raise HerdrError("Expected a local Windows named pipe from Herdr.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.WaitNamedPipeW.restype = wintypes.BOOL
    kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                    wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    kernel.PeekNamedPipe.restype = wintypes.BOOL
    if not kernel.WaitNamedPipeW(endpoint, int(timeout * 1000)):
        raise HerdrError("Herdr named pipe is unavailable: " + str(ctypes.get_last_error()))
    deadline = time.monotonic() + timeout
    with open(endpoint, "r+b", buffering=0) as pipe:
        pipe.write(payload)
        handle = msvcrt.get_osfhandle(pipe.fileno())

        def read():
            while time.monotonic() < deadline:
                available = wintypes.DWORD()
                if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                    raise HerdrError("Herdr named pipe read failed: " + str(ctypes.get_last_error()))
                if available.value:
                    return pipe.read(min(available.value, 65536))
                time.sleep(0.01)
            raise HerdrError("Timed out waiting for Herdr's named pipe response.")
        return _read_response(read, request_id)


def workspace_label(project):
    canonical = str(Path(project).resolve())
    key = hashlib.sha256(os.path.normcase(canonical).encode()).hexdigest()[:10]
    return Path(project).name + " [cockpit:" + key + "]"


def editor_key(project, session="dev-cockpit"):
    """Return a stable per-session, per-worktree editor identifier."""
    from .editor import project_identity
    return project_identity(project, session)


def pane_environment(project, session="dev-cockpit"):
    project = str(Path(project).resolve())
    return {
        "DEV_COCKPIT_PROJECT": project,
        "DEV_COCKPIT_HERDR_SESSION": session,
        "DEV_COCKPIT_EDITOR_KEY": editor_key(project, session),
    }


def layout_tree(project, agent_command, files_command=None, *, editor_command=None,
                session="dev-cockpit", layout="classic"):
    cwd = str(Path(project).resolve())
    if layout not in ("classic", "code"):
        raise ValueError("Layout must be 'code' or 'classic'.")
    if layout == "code":
        if not editor_command:
            raise ValueError("The code layout requires an editor command.")
        context = pane_environment(project, session)
        return {"type": "split", "direction": "down", "ratio": 0.78,
                "first": {"type": "split", "direction": "right", "ratio": 0.68,
                          "first": {"type": "pane", "label": "Editor", "cwd": cwd,
                                    "command": list(editor_command), "env": context},
                          "second": {"type": "pane", "label": "OMP", "cwd": cwd,
                                     "command": list(agent_command), "env": context}},
                "second": {"type": "pane", "label": "Shell", "cwd": cwd,
                           "env": context}}
    files_command = files_command or ["yazi", cwd]
    return {"type": "split", "direction": "down", "ratio": 0.75,
            "first": {"type": "split", "direction": "right", "ratio": 0.72,
                      "first": {"type": "pane", "label": "OMP", "cwd": cwd, "command": agent_command},
                      "second": {"type": "pane", "label": "Files", "cwd": cwd, "command": files_command}},
            "second": {"type": "pane", "label": "Shell", "cwd": cwd}}


def _workspace(client, project):
    label = workspace_label(project)
    existing = client.cli("workspace", "list").get("workspaces", [])
    return next((item for item in existing if item.get("label") == label), None)


def ensure_workspace(client, project, agent_command=None, files_command=None, *,
                     editor_command=None, session="dev-cockpit", layout="classic"):
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    label = workspace_label(project)
    existing = _workspace(client, project)
    if existing:
        client.cli("workspace", "focus", existing["workspace_id"])
        return {"created": False, "workspace_id": existing["workspace_id"], "label": label}
    agent_command = agent_command or ["omp"]
    files_command = files_command or ["yazi", str(project)]
    created = client.cli("workspace", "create", "--cwd", str(project), "--label", label, "--no-focus")
    workspace_id = created["workspace"]["workspace_id"]
    try:
        result = client.request("layout.apply", {"tab_id": created["tab"]["tab_id"],
                               "tab_label": "Code" if layout == "code" else "Cockpit",
                               "focus": True,
                               "root": layout_tree(project, agent_command, files_command,
                                                   editor_command=editor_command,
                                                   session=session, layout=layout)})
    except Exception as error:
        # The new workspace is retained, never blindly closed after an uncertain
        # API result (a process may already be running there).
        raise HerdrError("Workspace " + workspace_id + " was created, but layout provisioning failed. It was preserved for inspection: " + str(error)) from error
    return {"created": True, "workspace_id": workspace_id, "label": label, "layout": result}


def ensure_project_tab(client, project, label, command, *, session="dev-cockpit",
                       create_layout="classic", agent_command=None, editor_command=None):
    """Create or focus a single-purpose project tab without duplicating it."""
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    workspace = _workspace(client, project)
    if workspace is None:
        created_workspace = ensure_workspace(client, project, agent_command=agent_command,
                                             editor_command=editor_command, session=session,
                                             layout=create_layout)
        workspace_id = created_workspace["workspace_id"]
    else:
        workspace_id = workspace["workspace_id"]
    snapshot = client.cli("api", "snapshot").get("snapshot", {})
    tabs = [tab for tab in snapshot.get("tabs", [])
            if tab.get("workspace_id") == workspace_id and tab.get("label") == label]
    if len(tabs) > 1:
        raise HerdrError("Multiple " + label + " tabs exist in " + workspace_label(project) +
                         "; no tab was changed. Close or rename the duplicate manually.")
    if tabs:
        tab = tabs[0]
        panes = [pane for pane in snapshot.get("panes", [])
                 if pane.get("tab_id") == tab["tab_id"] and pane.get("label") == label]
        if len(panes) != 1:
            raise HerdrError("The existing " + label + " tab does not contain exactly one managed " +
                             label + " pane; no process was started or replaced.")
        client.request("tab.focus", {"tab_id": tab["tab_id"]})
        client.request("pane.focus", {"pane_id": panes[0]["pane_id"]})
        return {"created": False, "workspace_id": workspace_id,
                "tab_id": tab["tab_id"], "label": label}
    created = client.cli("tab", "create", "--workspace", workspace_id,
                         "--cwd", str(project), "--label", label, "--no-focus")
    tab = created["tab"]
    try:
        applied = client.request("layout.apply", {
            "tab_id": tab["tab_id"], "tab_label": label, "focus": True,
            "root": {"type": "pane", "label": label, "cwd": str(project),
                     "command": list(command), "env": pane_environment(project, session)},
        })
    except Exception as error:
        raise HerdrError("The " + label + " tab was created, but its command could not be applied. "
                         "It was preserved for inspection: " + str(error)) from error
    return {"created": True, "workspace_id": workspace_id,
            "tab_id": tab["tab_id"], "label": label, "layout": applied}


def focus_project_tab(project, label, command, *, session="dev-cockpit",
                      executable="herdr", env=None, attach=None,
                      create_layout="classic", agent_command=None,
                      editor_command=None):
    """Ensure a project tool tab and attach only when called outside Herdr."""
    inherited = os.environ if env is None else env
    client = Herdr(executable, session, env)
    client.ensure_server()
    result = ensure_project_tab(client, project, label, command, session=session,
                                create_layout=create_layout,
                                agent_command=agent_command,
                                editor_command=editor_command)
    print(("Created" if result["created"] else "Focused") + " " + label +
          " tab in " + workspace_label(project))
    if attach is None:
        attach = not (inherited.get("HERDR_ENV") or inherited.get("HERDR_PANE_ID"))
    if attach:
        return client.attach()
    return result


def ensure_code_editor(client, project, workspace_id, editor_command, *,
                       session="dev-cockpit", agent_command=None):
    """Focus a managed editor pane or add one tab to a classic workspace."""
    snapshot = client.cli("api", "snapshot").get("snapshot", {})
    panes = [pane for pane in snapshot.get("panes", [])
             if pane.get("workspace_id") == workspace_id and pane.get("label") == "Editor"]
    if len(panes) > 1:
        raise HerdrError("Multiple managed Editor panes exist in " + workspace_label(project) +
                         "; no pane was focused or replaced.")
    if panes:
        client.request("tab.focus", {"tab_id": panes[0]["tab_id"]})
        client.request("pane.focus", {"pane_id": panes[0]["pane_id"]})
        return {"created": False, "workspace_id": workspace_id,
                "tab_id": panes[0]["tab_id"], "label": "Editor"}
    return ensure_project_tab(client, project, "Editor", editor_command,
                              session=session, create_layout="classic",
                              agent_command=agent_command,
                              editor_command=editor_command)


def launch(project, *, session="dev-cockpit", executable="herdr", attach=True,
           env=None, agent_command=None, files_command=None, editor_command=None,
           layout="classic"):
    if layout == "code" and not editor_command:
        raise ValueError("The code layout requires an editor command.")
    client = Herdr(executable, session, env)
    client.ensure_server()
    if agent_command is None:
        from .intelligence import omp_command
        agent_command = omp_command(Path(project))
    result = ensure_workspace(client, project, agent_command, files_command,
                              editor_command=editor_command, session=session, layout=layout)
    if layout == "code" and not result["created"]:
        ensure_code_editor(client, project, result["workspace_id"], editor_command,
                           session=session, agent_command=agent_command)
    print(("Created" if result["created"] else "Reusing") + " Herdr workspace: " + result["label"])
    if attach:
        return client.attach()
    return result
