"""Native, additive package installation with verified download reuse.

Package-manager software remains owned by its manager. Direct release installs
are tracked byte-for-byte so interrupted installs can be repaired from cache.
Existing unmanaged binaries/configuration are never replaced by a setup rerun.
"""
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import shutil
import stat
import subprocess
import tempfile

from .downloads import download, extract_archive, sha256_file

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ('core', 'cockpit', 'terminal', 'history', 'extras', 'gestures')


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _reject_links(path):
    for entry in (path, *path.parents):
        reparse = entry.exists() and bool(getattr(entry.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
        if entry.is_symlink() or reparse:
            raise ValueError('Refusing symlink/junction in managed package path: ' + str(entry))


def _atomic_json(path, value):
    _reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def _read(command):
    return subprocess.run([str(x) for x in command], capture_output=True, text=True, check=False)


def refresh_path(target, home=None):
    """Refresh this process after package installation without changing profiles."""
    home = Path(home or Path.home())
    paths = [home / '.local/bin', home / '.cargo/bin', home / '.bun/bin']
    if target == 'windows':
        # Read installer-updated registry PATH in the same PowerShell invocation.
        try:
            import winreg
            for key, sub in [(winreg.HKEY_CURRENT_USER, 'Environment'),
                             (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')]:
                try:
                    with winreg.OpenKey(key, sub) as handle:
                        value, _ = winreg.QueryValueEx(handle, 'Path')
                        paths += [Path(os.path.expandvars(p)) for p in value.split(';') if p]
                except OSError:
                    pass
        except ImportError:
            pass
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local'))
        paths += [local / 'Microsoft/WinGet/Links', local / 'Microsoft/WindowsApps',
                  home / 'AppData/Roaming/npm']
    else:
        paths += [Path('/opt/homebrew/bin'), Path('/usr/local/bin'), Path('/home/linuxbrew/.linuxbrew/bin'),
                  Path('/Applications/Ghostty.app/Contents/MacOS'), home / 'Applications/Ghostty.app/Contents/MacOS']
    separator = os.pathsep
    old = os.environ.get('PATH', '').split(separator)
    additions = [str(p) for p in paths if p.is_dir() and str(p) not in old]
    if additions:
        os.environ['PATH'] = separator.join(additions + old)
    return os.environ.get('PATH', '')


def _known_paths(tool, target, home):
    name = tool.get('binary')
    if not name:
        return []
    suffix = '.exe' if target == 'windows' else ''
    paths = [home / '.local/bin' / (name + suffix)]
    if target == 'macos':
        paths += [Path('/opt/homebrew/bin') / name, Path('/usr/local/bin') / name]
        if name == 'ghostty':
            paths += [Path('/Applications/Ghostty.app/Contents/MacOS/ghostty'), home / 'Applications/Ghostty.app/Contents/MacOS/ghostty']
    elif target == 'linux':
        paths += [Path('/home/linuxbrew/.linuxbrew/bin') / name, Path('/snap/bin') / name]
    else:
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local'))
        program = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
        paths += [local / 'Microsoft/WinGet/Links' / (name + suffix)]
        locations = {'git': ['Git/cmd/git.exe', 'Git/bin/git.exe'], 'gh': ['GitHub CLI/gh.exe'],
                     'wezterm': ['WezTerm/wezterm.exe'], 'starship': ['starship/bin/starship.exe']}
        paths += [program / p for p in locations.get(name, [])]
        if name == 'omp':
            paths += [home / '.omp/bin/omp.exe', home / '.bun/bin/omp.exe']
        if name == 'herdr':
            paths += [local / 'herdr/bin/herdr.exe', local / 'herdr/current/herdr.exe', home / '.herdr/bin/herdr.exe']
    return paths


def find_tool(tool, target, home=None):
    """Locate an executable, including GUI apps and paths changed this install."""
    home = Path(home or Path.home())
    name = tool.get('binary') if isinstance(tool, dict) else str(tool)
    if not name:
        return None
    found = shutil.which(name)
    if found:
        return found
    for candidate in _known_paths({'binary': name}, target, home):
        if candidate.is_file() and (target == 'windows' or os.access(candidate, os.X_OK)):
            return str(candidate)
    return None


def package_plan(target, profiles, *, root=ROOT):
    result = []
    for original in _json(Path(root) / 'manifests/tools.json')['tools']:
        if original['profile'] not in profiles and 'all' not in profiles:
            continue
        spec = original['platforms'].get(target)
        if spec is None:
            continue
        tool = dict(original, target=target, spec=spec)
        adapter = spec['adapter']
        if adapter == 'brew':
            command = ['brew', 'install', *(['--cask'] if spec.get('cask') else []), spec['package']]
        elif adapter == 'winget':
            command = ['winget', 'install', '--exact', '--id', spec['package'], '--source', 'winget', '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity']
        else:
            command = ['dev-cockpit', 'install-' + adapter, tool['id']]
        result.append((tool, command, None))
    return result


def _manager_present(tool):
    spec = tool['spec']
    manager = spec['adapter']
    if manager == 'brew' and shutil.which('brew'):
        result = _read(['brew', 'list', '--versions', *(['--cask'] if spec.get('cask') else []), spec['package']])
        return result.returncode == 0 and bool(result.stdout.strip())
    if manager == 'winget' and shutil.which('winget'):
        result = _read(['winget', 'list', '--exact', '--id', spec['package'], '--source', 'winget', '--accept-source-agreements', '--disable-interactivity'])
        # Do not interpret a source/network failure as an absent package.
        if result.returncode not in (0, -1978335212, 2316632084):
            raise ValueError('Could not inspect installed WinGet package ' + spec['package'] + ': ' + (result.stderr or result.stdout).strip())
        return result.returncode == 0
    return False


def linux_release():
    values = {}
    try:
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                values[k] = v.strip('"')
    except OSError:
        pass
    return values


def _sudo(command):
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        return command
    if not shutil.which('sudo'):
        raise ValueError('sudo is required to install operating-system prerequisites')
    return ['sudo', *command]


def ensure_homebrew(target, cache_dir, downloads):
    refresh_path(target)
    if shutil.which('brew'):
        return
    if target == 'linux':
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            raise ValueError('Run setup as your normal user (with sudo available); Homebrew refuses root-owned installations')
        if shutil.which('apt-get'):
            _run(_sudo(['apt-get', 'update']))
            _run(_sudo(['apt-get', 'install', '-y', 'build-essential', 'procps', 'curl', 'file', 'git', 'ca-certificates']))
        elif shutil.which('dnf'):
            _run(_sudo(['dnf', 'install', '-y', 'procps-ng', 'curl', 'file', 'git', 'gcc', 'gcc-c++', 'make', 'glibc-langpack-en']))
        elif shutil.which('pacman'):
            _run(_sudo(['pacman', '-S', '--needed', '--noconfirm', 'base-devel', 'procps-ng', 'curl', 'file', 'git']))
        else:
            raise ValueError('Automatic Homebrew prerequisites support Ubuntu/Debian, Fedora and Arch; install Homebrew first on other Linux distributions')
    if target == 'macos':
        # Homebrew's noninteractive installer checks sudo without prompting.
        # Obtain the normal OS authorization first when brew is absent.
        _run(['sudo', '-v'])
    spec = downloads['sources']['homebrew']
    script = download(spec['url'], spec['sha256'], cache_dir)
    env = dict(os.environ, NONINTERACTIVE='1')
    _run(['/bin/bash', script], env=env)
    refresh_path(target)
    if not shutil.which('brew'):
        raise ValueError('Homebrew installation completed but brew could not be found')


def _arch(target):
    arch = platform.machine().lower()
    if arch in ('arm64', 'aarch64'):
        return 'arm64'
    if arch in ('x86_64', 'amd64', 'x64'):
        return 'x64'
    raise ValueError('Unsupported CPU architecture: ' + arch)


def _asset_name(tool, target):
    arch = _arch(target)
    if tool == 'herdr':
        # Upstream explicitly supports x64 Windows under ARM64 emulation.
        return 'herdr-windows-x86_64.zip' if target == 'windows' else 'herdr-' + target + '-' + ('aarch64' if arch == 'arm64' else 'x86_64')
    if tool == 'omp':
        label = 'darwin' if target == 'macos' else target
        return 'omp-' + label + '-' + arch + ('.exe' if target == 'windows' else '')
    raise ValueError('Unknown release adapter ' + tool)


def _receipt_path(home, tool):
    return home / '.local/share/dev-cockpit/packages' / (tool + '.json')


def _receipt(home, tool):
    home = Path(home).resolve()
    path = _receipt_path(home, tool)
    _reject_links(path)
    if not path.exists():
        return None
    value = _json(path)
    if not isinstance(value, dict) or not isinstance(value.get('files'), dict):
        raise ValueError('Invalid package receipt: ' + str(path))
    prefixes = ('.local/bin/',) if tool in ('herdr', 'omp') else ('Library/Fonts/', '.local/share/fonts/', 'AppData/Local/Microsoft/Windows/Fonts/')
    for relative, digest in value['files'].items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError('Invalid package receipt entry: ' + str(path))
        normalized = relative.replace('\\', '/')
        parts = PurePosixPath(normalized)
        if parts.is_absolute() or '..' in parts.parts or ':' in normalized or not normalized.startswith(prefixes):
            raise ValueError('Unsafe package receipt destination: ' + relative)
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid package receipt checksum: ' + str(path))
        _reject_links(home / relative)
    return value


def _receipt_condition(receipt, home):
    home = Path(home).resolve()
    if not receipt or not receipt['files']:
        return 'missing'
    missing = False
    for relative, expected in receipt['files'].items():
        path = home / relative
        _reject_links(path)
        if not path.exists():
            missing = True
        elif not path.is_file() or sha256_file(path) != expected:
            # A self-update or custom build belongs to the user. Setup must not
            # downgrade it to the old pin merely because its receipt differs.
            return 'changed'
    return 'missing' if missing else 'complete'


def _receipt_complete(receipt, home):
    return _receipt_condition(receipt, Path(home).resolve()) == 'complete'


def _install_files(files, home, tool_id, version, source_sha):
    """Validate all destinations before copying; ledger records only managed paths."""
    home = Path(home).resolve()
    old = _receipt(home, tool_id)
    known = old['files'] if old else {}
    desired = {}
    for source, relative, executable in files:
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe managed destination')
        target = home / relative
        _reject_links(target)
        expected = sha256_file(source)
        if target.exists():
            current = sha256_file(target)
            if str(relative) not in known and current != expected:
                raise ValueError('Preserving unmanaged file; cannot install ' + str(target))
            if str(relative) in known and current != known[str(relative)] and current != expected:
                raise ValueError('Preserving changed managed file; cannot repair ' + str(target))
        # Repairs only touch files listed in this tool's receipt. An interrupted
        # first install can also safely adopt exact copies of verified assets.
        desired[str(relative)] = expected
    for source, relative, executable in files:
        target = home / relative
        if not target.exists() or sha256_file(target) != desired[str(relative)]:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.cockpit-package-', dir=target.parent)
            os.close(fd)
            try:
                shutil.copyfile(source, name)
                if executable:
                    Path(name).chmod(0o755)
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        elif executable and os.name != 'nt':
            target.chmod(target.stat().st_mode | 0o111)
    _atomic_json(_receipt_path(home, tool_id), {'version': version, 'source_sha256': source_sha, 'files': desired})


def install_release(tool, home, cache, downloads):
    target = tool['target']
    source = downloads['sources'][tool['id']]
    asset = source['assets'][_asset_name(tool['id'], target)]
    archive = download(asset['url'], asset['sha256'], cache)
    if target == 'windows' and tool['id'] == 'herdr':
        with tempfile.TemporaryDirectory(prefix='cockpit-herdr-') as temp:
            extract_archive(archive, temp)
            files = [(p, Path('.local/bin') / p.relative_to(temp), p.suffix.lower() == '.exe') for p in Path(temp).rglob('*') if p.is_file()]
            _install_files(files, home, tool['id'], source['version'], asset['sha256'])
    else:
        name = tool['binary'] + ('.exe' if target == 'windows' else '')
        _install_files([(archive, Path('.local/bin') / name, True)], home, tool['id'], source['version'], asset['sha256'])


def _font_dirs(target, home):
    if target == 'macos':
        return [home / 'Library/Fonts', Path('/Library/Fonts')]
    if target == 'windows':
        return [Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local')) / 'Microsoft/Windows/Fonts', Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts']
    return [home / '.local/share/fonts', home / '.fonts', Path('/usr/share/fonts'), Path('/usr/local/share/fonts')]


def _font_present(target, home):
    return any(any(p.rglob('JetBrainsMonoNerdFont-Regular.ttf')) for p in _font_dirs(target, home) if p.is_dir())


def _font_registered(home):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
            for style in ('Regular', 'Bold', 'Italic', 'BoldItalic'):
                name = 'JetBrainsMonoNerdFont-' + style
                value, _ = winreg.QueryValueEx(key, name + ' (TrueType)')
                if not Path(value).is_file():
                    return False
        return True
    except (ImportError, OSError):
        return False


def install_font(tool, home, cache, downloads):
    source = downloads['sources']['font']
    asset = source['assets']['JetBrainsMono.zip']
    archive = download(asset['url'], asset['sha256'], cache)
    target = tool['target']
    # Deliberately use the selected home; tests never write to real LOCALAPPDATA.
    base = {'macos': Path('Library/Fonts'), 'linux': Path('.local/share/fonts'), 'windows': Path('AppData/Local/Microsoft/Windows/Fonts')}[target]
    with tempfile.TemporaryDirectory(prefix='cockpit-font-') as temp:
        extract_archive(archive, temp)
        selected = [p for p in Path(temp).rglob('JetBrainsMonoNerdFont-*.ttf') if p.name in ('JetBrainsMonoNerdFont-Regular.ttf', 'JetBrainsMonoNerdFont-Bold.ttf', 'JetBrainsMonoNerdFont-Italic.ttf', 'JetBrainsMonoNerdFont-BoldItalic.ttf')]
        if len(selected) != 4:
            raise ValueError('Unexpected Nerd Font archive layout')
        _install_files([(p, base / p.name, False) for p in selected], home, tool['id'], source['version'], asset['sha256'])
    if target == 'linux' and shutil.which('fc-cache'):
        _run(['fc-cache', str(home / base)])
    elif target == 'windows':
        import ctypes
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
            for p in selected:
                installed = home / base / p.name
                winreg.SetValueEx(key, p.stem + ' (TrueType)', 0, winreg.REG_SZ, str(installed))
                ctypes.windll.gdi32.AddFontResourceExW(str(installed), 0, 0)
        # Tell already running terminal/font pickers about the added faces.
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xffff, 0x001D, 0, 0, 2, 1000, ctypes.byref(result))


def _ghostty_command(downloads, cache=None):
    release = linux_release()
    distro, version = release.get('ID'), release.get('VERSION_ID')
    if distro == 'ubuntu' and version and tuple(int(n) for n in version.split('.')[:2]) >= (26, 4):
        return _sudo(['apt-get', 'install', '-y', 'ghostty'])
    if distro in ('arch', 'endeavouros', 'manjaro'):
        return _sudo(['pacman', '-S', '--needed', '--noconfirm', 'ghostty'])
    if distro in ('opensuse-tumbleweed', 'opensuse-leap'):
        return _sudo(['zypper', '--non-interactive', 'install', 'ghostty'])
    name = 'trixie' if distro == 'debian' and version == '13' else version
    if not ((distro == 'ubuntu' and version in ('24.04', '25.10')) or (distro == 'debian' and version == '13')):
        raise ValueError('Ghostty automatic Linux installation supports Ubuntu 24.04/25.10/26.04+, Debian 13, Arch and openSUSE. Install Ghostty first on this distro, then rerun; other profiles remain available.')
    arch = 'arm64' if _arch('linux') == 'arm64' else 'amd64'
    source = downloads['sources']['ghostty-deb']
    match = [a for n, a in source['assets'].items() if n.endswith('_' + arch + '_' + name + '.deb')]
    if len(match) != 1:
        raise ValueError('No pinned Ghostty package for this distribution/architecture')
    if cache is None:
        return ['apt-get', 'install', '-y', '<verified Ghostty .deb>']
    archive = download(match[0]['url'], match[0]['sha256'], cache)
    # A .deb suffix is required for apt to interpret the argument as a file.
    deb = Path(cache) / (match[0]['sha256'] + '.deb')
    if not deb.exists() or sha256_file(deb) != match[0]['sha256']:
        shutil.copyfile(archive, deb)
    deb.chmod(0o644)
    return _sudo(['apt-get', 'install', '-y', str(deb.resolve())])


def _present(tool, home, inspect_managers=True):
    adapter = tool['spec']['adapter']
    if adapter in ('release', 'font'):
        receipt = _receipt(home, tool['id'])
        if receipt:
            condition = _receipt_condition(receipt, home)
            if condition == 'changed':
                return 'user-updated managed installation (preserved)'
            complete = condition == 'complete'
            if complete and adapter == 'font' and tool['target'] == 'windows':
                complete = _font_registered(home)
            return 'verified managed installation' if complete else None
    if adapter == 'font':
        return 'existing Nerd Font' if _font_present(tool['target'], home) else None
    found = find_tool(tool, tool['target'], home)
    if found:
        return found
    if inspect_managers and _manager_present(tool):
        return 'installed package (PATH may need refresh)'
    return None


def run_packages(plan, install=False, *, home=None, cache_dir=None):
    home = Path(home or Path.home()).resolve()
    target = plan[0][0]['target'] if plan else None
    if install and target:
        refresh_path(target, home)
    cache = Path(cache_dir or os.environ.get('DEV_COCKPIT_CACHE', home / '.cache/dev-cockpit')) / 'downloads'
    downloads = _json(ROOT / 'manifests/downloads.json')
    pending, results = [], []
    for tool, command, _ in plan:
        present = _present(tool, home, inspect_managers=install)
        if present:
            print('PRESENT', tool['id'], present)
            results.append({'id': tool['id'], 'status': 'present'})
        else:
            print('PACKAGE', tool['id'], ':', shlex.join(command))
            pending.append((tool, command))
    if not install:
        return results + [{'id': tool['id'], 'status': 'planned'} for tool, _ in pending]
    # Check every platform adapter before installing any selected software.
    for tool, _ in pending:
        adapter = tool['spec']['adapter']
        if adapter == 'ghostty-linux':
            _ghostty_command(downloads)
        elif adapter == 'release':
            source = downloads['sources'][tool['id']]
            if _asset_name(tool['id'], target) not in source['assets']:
                raise ValueError('Missing pinned release for ' + tool['id'])
        elif adapter == 'winget' and not shutil.which('winget'):
            raise ValueError('WinGet is required. Run bootstrap/setup.ps1 -Install to provision it.')
    if any(t['spec']['adapter'] == 'brew' for t, _ in pending):
        ensure_homebrew(target, cache, downloads)
    for tool, command in pending:
        # Prerequisite managers may have installed dependencies already.
        present = _present(tool, home)
        if present:
            print('PRESENT', tool['id'], present)
            results.append({'id': tool['id'], 'status': 'present'})
            continue
        adapter = tool['spec']['adapter']
        if adapter == 'release':
            install_release(tool, home, cache, downloads)
        elif adapter == 'font':
            install_font(tool, home, cache, downloads)
        elif adapter == 'ghostty-linux':
            _run(_ghostty_command(downloads, cache))
        else:
            env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE='1', HOMEBREW_NO_INSTALL_UPGRADE='1')
            _run(command, env=env)
        refresh_path(target, home)
        if not _present(tool, home):
            raise ValueError('Installer returned success but ' + tool['id'] + ' was not found; rerun to repair the incomplete installation')
        results.append({'id': tool['id'], 'status': 'installed'})
    return results


def gesture_bridge_app(home=None):
    """Return the Hammerspoon app bundle path, or None when it is not installed."""
    home = Path(home or Path.home())
    for candidate in (Path('/Applications/Hammerspoon.app'), home / 'Applications/Hammerspoon.app'):
        if candidate.exists():
            return candidate
    return None


def launch_gesture_bridge(target, profiles, *, home=None):
    """Start Hammerspoon so the pinch-to-zoom bridge is live after install.

    macOS-only and opt-in: returns None on other targets, when the gestures
    profile is not selected, or when the cask is not installed. The Accessibility
    grant is manual and cannot be verified from the CLI, so this only launches the
    app; the bridge itself reports whether it actually started.
    """
    if target != 'macos' or 'gestures' not in profiles:
        return None
    app = gesture_bridge_app(home)
    if app is None:
        return None
    result = _read(['open', '-a', str(app)])
    if result.returncode != 0:
        return 'could not launch Hammerspoon: ' + (result.stderr or result.stdout).strip()
    return 'launched Hammerspoon'


def doctor(plan, *, home=None):
    home = Path(home or Path.home()).resolve()
    if plan:
        refresh_path(plan[0][0]['target'], home)
    missing = []
    for tool, _, _ in plan:
        location = _present(tool, home)
        print('FOUND' if location else 'MISSING', tool['id'], location or '')
        if not location:
            missing.append(tool['id'])
    return 1 if missing else 0
