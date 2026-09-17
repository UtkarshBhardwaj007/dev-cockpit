"""Content-addressed persistent CLI deployment for one-line installations."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .configuration import configuration_lock, reject_links

RUNTIME_PATHS = ("bootstrap", "dev_cockpit", "config", "manifests", "docs", "licenses", "README.md", "LICENSE")


def runtime_files(root):
    root = Path(root).resolve()
    files = {}
    for name in RUNTIME_PATHS:
        entry = root / name
        candidates = entry.rglob("*") if entry.is_dir() else [entry]
        for path in candidates:
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                continue
            reject_links(path)
            if path.is_file():
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "bootstrap/cockpit.py" not in files or "dev_cockpit/cli.py" not in files:
        raise ValueError("Incomplete dev-cockpit runtime source")
    return dict(sorted(files.items()))


def runtime_directory(home):
    return Path(home).resolve() / ".local/share/dev-cockpit/runtime"


def deploy_runtime(root, home):
    files = runtime_files(root)
    version = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    base = runtime_directory(home)
    target = base / version
    reject_links(target)
    with configuration_lock(base):
        if target.exists():
            if runtime_files(target) != files:
                raise ValueError("Installed runtime was modified; preserved for inspection: " + str(target))
            print("REUSE runtime", version)
            return target
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=base) as temporary:
            staging = Path(temporary) / "runtime"
            staging.mkdir()
            for relative in files:
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(root) / relative, destination)
            if runtime_files(staging) != files:
                raise ValueError("Runtime source changed during installation; retry setup")
            staging.rename(target)
    print("INSTALLED runtime", version)
    return target
