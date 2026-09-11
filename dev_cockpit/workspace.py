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


def layout_tree(project, agent_command, files_command):
    cwd = str(Path(project).resolve())
    return {"type": "split", "direction": "down", "ratio": 0.75,
            "first": {"type": "split", "direction": "right", "ratio": 0.72,
                      "first": {"type": "pane", "label": "OMP", "cwd": cwd, "command": agent_command},
                      "second": {"type": "pane", "label": "Files", "cwd": cwd, "command": files_command}},
            "second": {"type": "pane", "label": "Shell", "cwd": cwd}}


def ensure_workspace(client, project, agent_command=None, files_command=None):
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    label = workspace_label(project)
    existing = client.cli("workspace", "list").get("workspaces", [])
    for workspace in existing:
        if workspace.get("label") == label:
            client.cli("workspace", "focus", workspace["workspace_id"])
            return {"created": False, "workspace_id": workspace["workspace_id"], "label": label}
    agent_command = agent_command or ["omp"]
    files_command = files_command or ["yazi", str(project)]
    created = client.cli("workspace", "create", "--cwd", str(project), "--label", label, "--no-focus")
    workspace_id = created["workspace"]["workspace_id"]
    try:
        result = client.request("layout.apply", {"tab_id": created["tab"]["tab_id"], "tab_label": "Cockpit",
                               "focus": True, "root": layout_tree(project, agent_command, files_command)})
    except Exception as error:
        # The new workspace is retained, never blindly closed after an uncertain
        # API result (a process may already be running there).
        raise HerdrError("Workspace " + workspace_id + " was created, but layout provisioning failed. It was preserved for inspection: " + str(error)) from error
    return {"created": True, "workspace_id": workspace_id, "label": label, "layout": result}


def launch(project, *, session="dev-cockpit", executable="herdr", attach=True,
           env=None, agent_command=None, files_command=None):
    client = Herdr(executable, session, env)
    client.ensure_server()
    if agent_command is None:
        from .intelligence import omp_command
        agent_command = omp_command(Path(project))
    result = ensure_workspace(client, project, agent_command, files_command)
    print(("Created" if result["created"] else "Reusing") + " Herdr workspace: " + result["label"])
    if attach:
        return client.attach()
    return result
