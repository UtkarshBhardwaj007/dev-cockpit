import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from dev_cockpit import downloads, packages


class FakeResponse(io.BytesIO):
    def geturl(self):
        return 'https://example.org/artifact'


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.data = b'official artifact bytes\0'
        self.sha = hashlib.sha256(self.data).hexdigest()

    def test_download_checks_hash_then_reuses_without_network(self):
        with patch('dev_cockpit.downloads.urllib.request.urlopen', return_value=FakeResponse(self.data)) as get:
            first = downloads.download('https://example.org/artifact', self.sha, self.cache)
            stamp = first.stat().st_mtime_ns
            second = downloads.download('https://example.org/artifact', self.sha, self.cache)
        self.assertEqual(first, second)
        self.assertEqual(first.read_bytes(), self.data)
        self.assertEqual(first.stat().st_mtime_ns, stamp)
        get.assert_called_once()

    def test_checksum_failure_never_publishes_or_keeps_partial(self):
        with patch('dev_cockpit.downloads.urllib.request.urlopen', return_value=FakeResponse(b'tampered')):
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                downloads.download('https://example.org/artifact', self.sha, self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_corrupt_cache_is_replaced_after_verification(self):
        (self.cache / self.sha).write_bytes(b'partial old file')
        with patch('dev_cockpit.downloads.urllib.request.urlopen', return_value=FakeResponse(self.data)) as get:
            self.assertEqual(downloads.download('https://example.org/a', self.sha, self.cache).read_bytes(), self.data)
        get.assert_called_once()

    def test_interrupted_download_keeps_existing_cache_and_removes_temp(self):
        (self.cache / self.sha).write_bytes(b'incomplete')
        with patch('dev_cockpit.downloads.urllib.request.urlopen', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                downloads.download('https://example.org/a', self.sha, self.cache)
        self.assertEqual([p.name for p in self.cache.iterdir()], [self.sha])

    def test_non_https_and_missing_checksum_are_rejected_before_io(self):
        with patch('dev_cockpit.downloads.urllib.request.urlopen') as get:
            for url, digest in [('http://example.org/a', self.sha), ('https://example.org/a', 'not-a-hash')]:
                with self.assertRaises(ValueError):
                    downloads.download(url, digest, self.cache)
        get.assert_not_called()

    def test_zip_slip_and_symlinks_are_rejected(self):
        for name in ('../outside', '/absolute', 'C:/Windows/pwn', '..\\outside'):
            file = self.cache / 'bad.zip'
            with zipfile.ZipFile(file, 'w') as bundle:
                bundle.writestr(name, b'bad')
            with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                downloads.extract_archive(file, self.cache / 'extract')
        file = self.cache / 'link.zip'
        with zipfile.ZipFile(file, 'w') as bundle:
            info = zipfile.ZipInfo('link')
            info.external_attr = 0o120777 << 16
            bundle.writestr(info, '../../outside')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            downloads.extract_archive(file, self.cache / 'extract')


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit install ' ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home with spaces'
        self.cache = Path(self.temp.name) / 'cache'
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(lambda: self.output.__exit__(None, None, None))
        self.env = patch.dict(os.environ, dict(os.environ), clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def tool(self, id, target='linux'):
        return next(p for p in packages.package_plan(target, ['all']) if p[0]['id'] == id)

    def native_asset(self, data=b'#!/bin/sh\necho fake-version\n', target='linux', id='herdr'):
        sha = hashlib.sha256(data).hexdigest()
        self.cache.mkdir()
        path = self.cache / sha
        path.write_bytes(data)
        source = {'version': 'v1.2.3', 'assets': {packages._asset_name(id, target): {'url': 'https://example.org/release', 'sha256': sha}}}
        return path, {'sources': {id: source}}

    def test_all_supported_profiles_have_real_adapters(self):
        for target in ('macos', 'linux', 'windows'):
            plan = packages.package_plan(target, ['all'])
            self.assertGreaterEqual(len(plan), 20)
            self.assertFalse(any(note for _, _, note in plan))
            self.assertEqual([t['id'] for t, _, _ in plan if t['profile'] == 'terminal'], ['wezterm', 'nerd-font'] if target == 'windows' else ['ghostty', 'nerd-font'])

    def test_preview_never_executes_commands_or_downloads_or_creates_dirs(self):
        with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages._font_present', return_value=False), patch('dev_cockpit.packages._read') as read, patch('dev_cockpit.packages._run') as run, patch('dev_cockpit.packages.download') as get:
            packages.run_packages(packages.package_plan('windows', ['all']), home=self.home)
        read.assert_not_called()
        run.assert_not_called()
        get.assert_not_called()
        self.assertFalse(self.home.exists())

    def test_existing_binary_never_installs_or_downloads(self):
        with patch('dev_cockpit.packages.find_tool', return_value='/existing/herdr'), patch('dev_cockpit.packages.download') as get, patch('dev_cockpit.packages._run') as run:
            result = packages.run_packages([self.tool('herdr')], install=True, home=self.home)
        self.assertEqual(result, [{'id': 'herdr', 'status': 'present'}])
        get.assert_not_called()
        run.assert_not_called()

    def test_manager_installed_without_path_never_reinstalls(self):
        for target in ('macos', 'windows'):
            with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages.shutil.which', return_value='/manager'), patch('dev_cockpit.packages._read', return_value=subprocess.CompletedProcess([], 0, 'installed package\n', '')), patch('dev_cockpit.packages.download') as get, patch('dev_cockpit.packages._run') as run:
                result = packages.run_packages([self.tool('git', target)], install=True, home=self.home)
            self.assertEqual(result, [{'id': 'git', 'status': 'present'}])
            get.assert_not_called()
            run.assert_not_called()

    def test_manager_inspection_failure_does_not_trigger_reinstall(self):
        with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages.shutil.which', return_value='/winget'), patch('dev_cockpit.packages._read', return_value=subprocess.CompletedProcess([], 5, '', 'source unavailable')), patch('dev_cockpit.packages._run') as run:
            with self.assertRaisesRegex(ValueError, 'Could not inspect'):
                packages.run_packages([self.tool('git', 'windows')], install=True, home=self.home)
        run.assert_not_called()

    def test_macos_gui_is_found_without_path(self):
        executable = self.home / 'Applications/Ghostty.app/Contents/MacOS/ghostty'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'fake')
        executable.chmod(0o755)
        with patch('dev_cockpit.packages.shutil.which', return_value=None), patch('dev_cockpit.packages._known_paths', return_value=[executable]):
            self.assertEqual(packages.find_tool('ghostty', 'macos', self.home), str(executable))

    def test_managed_release_repeat_skips_all_downloads(self):
        path, sources = self.native_asset()
        tool = self.tool('herdr')[0]
        with patch('dev_cockpit.packages.download', return_value=path):
            packages.install_release(tool, self.home, self.cache, sources)
        with patch('dev_cockpit.packages.download') as get, patch('dev_cockpit.packages._run') as run:
            result = packages.run_packages([self.tool('herdr')], install=True, home=self.home, cache_dir=self.cache)
        self.assertEqual(result[0]['status'], 'present')
        get.assert_not_called()
        run.assert_not_called()

    def test_missing_managed_binary_repairs_from_local_cache_without_network(self):
        path, sources = self.native_asset()
        tool = self.tool('herdr')[0]
        packages.install_release(tool, self.home, self.cache, sources)
        binary = self.home / '.local/bin/herdr'
        binary.unlink()
        with patch('dev_cockpit.downloads.urllib.request.urlopen') as network:
            packages.install_release(tool, self.home, self.cache, sources)
        network.assert_not_called()
        self.assertEqual(binary.read_bytes(), path.read_bytes())

    def test_windows_release_preserves_conpty_and_repairs_missing_dll(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as bundle:
            bundle.writestr('herdr.exe', b'fake-exe')
            bundle.writestr('conpty/conpty.dll', b'required-dll')
            bundle.writestr('conpty/x64/OpenConsole.exe', b'required-helper')
        path, sources = self.native_asset(data.getvalue(), 'windows')
        tool = self.tool('herdr', 'windows')[0]
        packages.install_release(tool, self.home, self.cache, sources)
        dll = self.home / '.local/bin/conpty/conpty.dll'
        dll.unlink()
        self.assertIsNone(packages._present(tool, self.home))
        with patch('dev_cockpit.downloads.urllib.request.urlopen') as network:
            packages.install_release(tool, self.home, self.cache, sources)
        network.assert_not_called()
        self.assertEqual(dll.read_bytes(), b'required-dll')
        self.assertTrue(packages._receipt_complete(packages._receipt(self.home, 'herdr'), self.home))

    def test_preexisting_unmanaged_native_file_is_preserved(self):
        source, sources = self.native_asset()
        binary = self.home / '.local/bin/herdr'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'my custom build')
        with self.assertRaisesRegex(ValueError, 'Preserving unmanaged file'):
            packages.install_release(self.tool('herdr')[0], self.home, self.cache, sources)
        self.assertEqual(binary.read_bytes(), b'my custom build')

    def test_interrupted_first_install_adopts_exact_verified_file(self):
        source, sources = self.native_asset()
        binary = self.home / '.local/bin/herdr'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(source.read_bytes())
        packages.install_release(self.tool('herdr')[0], self.home, self.cache, sources)
        self.assertTrue(packages._receipt_complete(packages._receipt(self.home, 'herdr'), self.home))

    def test_unsupported_ghostty_linux_preflights_before_any_install(self):
        with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages._manager_present', return_value=False), patch('dev_cockpit.packages.linux_release', return_value={'ID': 'unknown'}), patch('dev_cockpit.packages._run') as run, patch('dev_cockpit.packages.download') as get:
            with self.assertRaisesRegex(ValueError, 'Ghostty automatic Linux'):
                packages.run_packages([self.tool('git'), self.tool('ghostty')], install=True, home=self.home)
        get.assert_not_called()
        run.assert_not_called()

    def test_package_manager_failure_propagates_and_stops(self):
        with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages._manager_present', return_value=False), patch('dev_cockpit.packages.ensure_homebrew'), patch('dev_cockpit.packages._run', side_effect=subprocess.CalledProcessError(7, ['brew'])) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                packages.run_packages([self.tool('git'), self.tool('gh')], install=True, home=self.home)
        self.assertEqual(run.call_count, 1)

    def test_successful_manager_exit_without_installed_package_is_failure(self):
        with patch('dev_cockpit.packages.find_tool', return_value=None), patch('dev_cockpit.packages._manager_present', return_value=False), patch('dev_cockpit.packages.ensure_homebrew'), patch('dev_cockpit.packages._run'):
            with self.assertRaisesRegex(ValueError, 'returned success but git was not found'):
                packages.run_packages([self.tool('git')], install=True, home=self.home)

    def test_user_updated_managed_binary_is_preserved_without_download(self):
        source, sources = self.native_asset()
        tool = self.tool('herdr')[0]
        packages.install_release(tool, self.home, self.cache, sources)
        binary = self.home / '.local/bin/herdr'
        binary.write_bytes(b'#!/bin/sh\necho newer-upstream-version\n')
        updated = binary.read_bytes()
        with patch('dev_cockpit.packages.download') as get, patch('dev_cockpit.packages._run') as run:
            result = packages.run_packages([self.tool('herdr')], install=True, home=self.home, cache_dir=self.cache)
        self.assertEqual(result[0]['status'], 'present')
        self.assertEqual(binary.read_bytes(), updated)
        get.assert_not_called()
        run.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'Preserving changed managed file'):
            packages.install_release(tool, self.home, self.cache, sources)

    def test_tampered_receipt_cannot_read_outside_package_roots(self):
        receipt = packages._receipt_path(self.home, 'herdr')
        receipt.parent.mkdir(parents=True)
        for name in ('../../outside', '/absolute/path', 'C:/Windows/path', '.ssh/config'):
            receipt.write_text(json.dumps({'files': {name: '0' * 64}}))
            with self.assertRaisesRegex(ValueError, 'Unsafe package receipt'):
                packages._receipt(self.home, 'herdr')

    def test_package_symlink_destinations_are_rejected_before_writes(self):
        source, sources = self.native_asset()
        self.home.mkdir(parents=True)
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        try:
            (self.home / '.local').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Windows symlinks require developer mode or privileges')
        with self.assertRaisesRegex(ValueError, 'symlink/junction'):
            packages.install_release(self.tool('herdr')[0], self.home, self.cache, sources)
        self.assertEqual(list(outside.iterdir()), [])

    def test_supported_ubuntu_selects_pinned_deb_without_network_during_preflight(self):
        manifest = packages._json(packages.ROOT / 'manifests/downloads.json')
        with patch('dev_cockpit.packages.linux_release', return_value={'ID': 'ubuntu', 'VERSION_ID': '24.04'}), patch('dev_cockpit.packages.download') as get:
            command = packages._ghostty_command(manifest)
        self.assertEqual(command, ['apt-get', 'install', '-y', '<verified Ghostty .deb>'])
        get.assert_not_called()

    def test_windows_font_receipt_does_not_skip_missing_registration(self):
        tool = self.tool('nerd-font', 'windows')[0]
        with patch('dev_cockpit.packages._receipt', return_value={'files': {'font.ttf': 'hash'}}), patch('dev_cockpit.packages._receipt_condition', return_value='complete'), patch('dev_cockpit.packages._font_registered', return_value=False):
            self.assertIsNone(packages._present(tool, self.home))

    def test_windows_protected_inherited_localappdata_is_ignored(self):
        """Regression for #4: service-profile WindowsApps may deny traversal."""
        protected = Path('C:/Windows/system32/config/systemprofile/AppData/Local')
        user_local = self.home / 'AppData/Local'
        user_winget = user_local / 'Microsoft/WinGet/Links'
        user_winget.mkdir(parents=True)
        previous_is_dir = Path.is_dir

        def is_dir(path):
            if str(path).startswith(str(protected)):
                raise PermissionError(5, 'Access is denied', str(path))
            return previous_is_dir(path)

        with patch.dict(os.environ, {'LOCALAPPDATA': str(protected)}, clear=False), patch.object(Path, 'is_dir', is_dir):
            # run_packages calls refresh_path before it inspects or invokes any
            # installer; this matches the failure point in the report.
            with patch('dev_cockpit.packages.find_tool', return_value='C:/fixture/git.exe'):
                result = packages.run_packages([self.tool('git', 'windows')], install=True, home=self.home)
            refreshed = [Path(entry) for entry in os.environ['PATH'].split(os.pathsep) if entry]
            self.assertEqual(result, [{'id': 'git', 'status': 'present'}])
            # Windows may spell this temp path as its 8.3 alias in Path.
            self.assertTrue(any(entry.exists() and os.path.samefile(entry, user_winget) for entry in refreshed))
            self.assertFalse(packages._font_present('windows', self.home))

    def test_windows_paths_include_selected_home_when_localappdata_is_foreign(self):
        foreign = Path('C:/Windows/system32/config/systemprofile/AppData/Local')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(foreign)}, clear=False):
            paths = packages._known_paths({'binary': 'git'}, 'windows', self.home)
        self.assertIn(self.home / 'AppData/Local/Microsoft/WinGet/Links/git.exe', paths)

    def test_windows_herdr_paths_include_each_localappdata_candidate(self):
        foreign = Path('C:/Windows/system32/config/systemprofile/AppData/Local')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(foreign)}, clear=False):
            paths = packages._known_paths({'binary': 'herdr'}, 'windows', self.home)
        self.assertIn(self.home / 'AppData/Local/herdr/bin/herdr.exe', paths)
        self.assertIn(self.home / 'AppData/Local/herdr/current/herdr.exe', paths)

    def test_gestures_profile_is_macos_only(self):
        self.assertEqual([t['id'] for t, _, _ in packages.package_plan('macos', ['gestures'])], ['hammerspoon'])
        self.assertEqual(packages.package_plan('linux', ['gestures']), [])
        self.assertEqual(packages.package_plan('windows', ['gestures']), [])
        command = packages.package_plan('macos', ['gestures'])[0][1]
        self.assertEqual(command, ['brew', 'install', '--cask', 'hammerspoon'])

    def test_launch_gesture_bridge_is_macos_and_gestures_only(self):
        with patch('dev_cockpit.packages._read') as read:
            self.assertIsNone(packages.launch_gesture_bridge('linux', ['gestures']))
            self.assertIsNone(packages.launch_gesture_bridge('windows', ['gestures']))
            self.assertIsNone(packages.launch_gesture_bridge('macos', ['core']))
            read.assert_not_called()

    def test_launch_gesture_bridge_opens_hammerspoon_when_installed(self):
        app = Path('/Applications/Hammerspoon.app')
        with patch('dev_cockpit.packages.gesture_bridge_app', return_value=app), patch('dev_cockpit.packages._read', return_value=subprocess.CompletedProcess([], 0, '', '')) as read:
            message = packages.launch_gesture_bridge('macos', ['gestures'])
        self.assertEqual(message, 'launched Hammerspoon')
        read.assert_called_once_with(['open', '-a', str(app)])

    def test_launch_gesture_bridge_skips_when_app_is_absent(self):
        with patch('dev_cockpit.packages.gesture_bridge_app', return_value=None), patch('dev_cockpit.packages._read') as read:
            self.assertIsNone(packages.launch_gesture_bridge('macos', ['gestures']))
        read.assert_not_called()

    def test_launch_gesture_bridge_reports_launch_failure(self):
        app = Path('/Applications/Hammerspoon.app')
        failed = subprocess.CompletedProcess([], 1, '', 'not permitted')
        with patch('dev_cockpit.packages.gesture_bridge_app', return_value=app), patch('dev_cockpit.packages._read', return_value=failed):
            message = packages.launch_gesture_bridge('macos', ['gestures'])
        self.assertEqual(message, 'could not launch Hammerspoon: not permitted')

    def test_each_download_is_https_pinned_and_supported_native_assets_exist(self):
        manifest = packages._json(packages.ROOT / 'manifests/downloads.json')
        for source in manifest['sources'].values():
            for asset in source.get('assets', {'installer': source}).values():
                self.assertTrue(asset['url'].startswith('https://'))
                self.assertRegex(asset['sha256'], '^[0-9a-f]{64}$')
        for arch in ('x86_64', 'aarch64'):
            with patch('dev_cockpit.packages.platform.machine', return_value=arch):
                for target in ('macos', 'linux', 'windows'):
                    for name in ('herdr', 'omp'):
                        self.assertIn(packages._asset_name(name, target), manifest['sources'][name]['assets'])


if __name__ == '__main__':
    unittest.main()
