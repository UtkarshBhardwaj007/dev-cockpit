"""Checksum-addressed downloads; no external Python dependencies."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile


def sha256_file(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def download(url, sha256, cache_dir):
    """Reuse verified bytes, stage incomplete downloads, publish atomically.

    The expected digest must come from the checked-in release manifest, not a
    checksum fetched from the same mutable URL at install time.
    """
    if not url.startswith('https://'):
        raise ValueError('Downloads must use HTTPS')
    if len(sha256) != 64 or any(c not in '0123456789abcdef' for c in sha256):
        raise ValueError('A pinned SHA-256 digest is required')
    cache = Path(cache_dir)
    target = cache / sha256
    if target.is_file() and sha256_file(target) == sha256:
        return target
    cache.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=sha256 + '.', suffix='.part', dir=cache)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'dev-cockpit-bootstrap/1'})
        with os.fdopen(fd, 'wb') as dest, urllib.request.urlopen(request, timeout=120) as response:
            if not response.geturl().startswith('https://'):
                raise ValueError('Refusing download redirected outside HTTPS')
            shutil.copyfileobj(response, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
        if sha256_file(name) != sha256:
            raise ValueError('Checksum mismatch for ' + url)
        os.replace(name, target)
        return target
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _safe_name(name):
    # Reject Windows paths even when tests/install run on Unix.
    normalized = name.replace('\\', '/')
    path = PurePosixPath(normalized)
    if path.is_absolute() or '..' in path.parts or ':' in normalized:
        raise ValueError('Unsafe archive member: ' + name)
    return path


def extract_archive(archive, destination):
    """Extract only ordinary files/directories; never links or device nodes."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                path = _safe_name(member.filename)
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Archive symlinks are not supported')
                dest = destination.joinpath(*path.parts)
                if member.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, dest.open('wb') as output:
                        shutil.copyfileobj(source, output)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                path = _safe_name(member.name)
                dest = destination.joinpath(*path.parts)
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(member) as source, dest.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    dest.chmod(member.mode & 0o777)
                else:
                    raise ValueError('Archive links and special files are not supported')
