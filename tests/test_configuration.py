import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dev_cockpit import configuration as config

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit-config ' spaces ")
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "user home"
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        self.temp.cleanup()

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}

    def apply(self, target='linux', **kwargs):
        return config.manage_config(self.home, target, apply=True, **kwargs)

    def test_preview_is_read_only_on_all_platforms(self):
        for target in ['linux', 'macos', 'windows']:
            config.manage_config(self.home, target)
        self.assertFalse(self.home.exists())

    def test_apply_twice_preserves_content_and_mtime(self):
        for target in ['linux', 'macos', 'windows']:
            self.home = self.base / target
            self.apply(target)
            before = self.snapshot()
            self.assertEqual(self.apply(target), [])
            self.assertEqual(before, self.snapshot())

    def test_existing_settings_and_ssh_are_preserved(self):
        paths, ledger = config.config_targets(self.home, 'linux')
        for destination in [*paths.values(), self.home / '.gitconfig', self.home / '.ssh/config']:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'personal config\n')
        self.apply()
        for destination in paths.values():
            self.assertEqual(destination.read_bytes(), b'personal config\n')
        self.assertEqual(json.loads(ledger.read_text())['files'].keys(), {str(ledger.parent / 'environment.sh')})
        self.apply(uninstall=True)
        self.assertEqual((self.home / '.ssh/config').read_bytes(), b'personal config\n')
        self.assertEqual((self.home / '.gitconfig').read_bytes(), b'personal config\n')

    def test_profile_roundtrip_retains_exact_content_and_mode(self):
        self.home.mkdir()
        original = b'# existing profile\r\nexport MY_SETTING=1'
        profile = self.home / '.bashrc'
        profile.write_bytes(original)
        profile.chmod(0o640)
        self.apply()
        self.assertEqual(profile.read_bytes().count(config.BEGIN), 1)
        backups = list((self.home / '.config/dev-cockpit/backups').rglob('*.bak'))
        self.assertIn(original, [p.read_bytes() for p in backups])
        self.apply(uninstall=True)
        self.assertEqual(profile.read_bytes(), original)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(profile.stat().st_mode), 0o640)
        self.assertFalse((self.home / '.zshrc').exists())

    def test_profile_edit_outside_block_survives_uninstall(self):
        self.apply()
        profile = self.home / '.zshrc'
        profile.write_bytes(profile.read_bytes() + b'export PERSONAL=true\n')
        self.apply()
        self.apply(uninstall=True)
        self.assertEqual(profile.read_bytes(), b'export PERSONAL=true\n')

    def test_edited_block_is_never_overwritten_or_removed(self):
        self.apply()
        profile = self.home / '.bashrc'
        changed = profile.read_bytes().replace(b'# Managed activation only.', b'# User changed activation.')
        profile.write_bytes(changed)
        self.apply()
        self.apply(uninstall=True)
        self.assertEqual(profile.read_bytes(), changed)

    def test_manually_deleted_activation_stays_deleted(self):
        self.apply()
        profile = self.home / '.bashrc'
        profile.write_bytes(b'# user removed activation\n')
        self.apply()
        self.assertEqual(profile.read_bytes(), b'# user removed activation\n')

    def test_edited_managed_file_survives_uninstall(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        chosen = paths['config/starship/starship.toml']
        chosen.write_bytes(b'# my changes\n')
        self.apply()
        self.apply(uninstall=True)
        self.assertEqual(chosen.read_bytes(), b'# my changes\n')

    def test_owned_file_updated_when_repository_changes(self):
        self.apply()
        checkout = self.base / 'new checkout'
        shutil.copytree(ROOT / 'config', checkout / 'config')
        (checkout / 'config/starship/starship.toml').write_bytes(b'# new managed release\n')
        self.apply(root=checkout)
        paths, _ = config.config_targets(self.home, 'linux')
        self.assertEqual(paths['config/starship/starship.toml'].read_bytes(), b'# new managed release\n')

    def test_omp_is_not_replaced_by_release_updates(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        original = paths['config/omp/config.yml'].read_bytes()
        checkout = self.base / 'new checkout'
        shutil.copytree(ROOT / 'config', checkout / 'config')
        (checkout / 'config/omp/config.yml').write_bytes(b'# different default\n')
        self.apply(root=checkout)
        self.assertEqual(paths['config/omp/config.yml'].read_bytes(), original)

    def test_owned_herdr_config_updates_until_the_user_edits_it(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        checkout = self.base / 'new checkout'
        shutil.copytree(ROOT / 'config', checkout / 'config')
        (checkout / 'config/herdr/config.toml').write_bytes(b'# new managed release\n')
        self.apply(root=checkout)
        self.assertEqual(paths['config/herdr/config.toml'].read_bytes(), b'# new managed release\n')
        paths['config/herdr/config.toml'].write_bytes(b'# user edited\n')
        (checkout / 'config/herdr/config.toml').write_bytes(b'# another release\n')
        self.apply(root=checkout)
        self.assertEqual(paths['config/herdr/config.toml'].read_bytes(), b'# user edited\n')

    def test_force_config_repairs_edited_owned_files_with_backup(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        chosen = paths['config/starship/starship.toml']
        chosen.write_bytes(b'# my changes\n')
        self.apply(force=True)
        self.assertEqual(chosen.read_bytes(), (ROOT / 'config/starship/starship.toml').read_bytes())
        backups = [item.read_bytes() for item in (self.home / '.config/dev-cockpit/backups').rglob('*.bak')]
        self.assertIn(b'# my changes\n', backups)

    def test_force_config_repairs_edited_herdr_config(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        herdr = paths['config/herdr/config.toml']
        herdr.write_bytes(b'# herdr rewrote this\n')
        self.apply(force=True)
        self.assertEqual(herdr.read_bytes(), (ROOT / 'config/herdr/config.toml').read_bytes())

    def test_force_config_never_touches_user_created_files(self):
        paths, _ = config.config_targets(self.home, 'linux')
        chosen = paths['config/starship/starship.toml']
        chosen.parent.mkdir(parents=True, exist_ok=True)
        chosen.write_bytes(b'# my own prompt\n')
        self.apply(force=True)
        self.assertEqual(chosen.read_bytes(), b'# my own prompt\n')

    def test_yazi_behavior_config_is_installed(self):
        self.apply()
        paths, _ = config.config_targets(self.home, 'linux')
        behavior = paths['config/yazi/yazi.toml']
        keymap = paths['config/yazi/keymap.toml']
        self.assertTrue(behavior.is_file())
        self.assertTrue(keymap.is_file())
        self.assertIn(b'[opener]', behavior.read_bytes())
        self.assertIn(b'bat', behavior.read_bytes())
        self.assertIn(b'dev-edit -- %s', behavior.read_bytes())
        self.assertIn(b'dev-edit --standalone --wait -- %s', behavior.read_bytes())
        self.assertIn(b'External editor', behavior.read_bytes())
        self.assertIn(b'prepend_keymap', keymap.read_bytes())

    def test_fresh_preferences_are_macos_only_and_create_only(self):
        for target in ('linux', 'windows'):
            paths, _ = config.config_targets(self.home, target)
            self.assertNotIn('config/fresh/config.json', paths)
            self.assertNotIn('config/editor/editor.json', paths)
        paths, _ = config.config_targets(self.home, 'macos')
        fresh = paths['config/fresh/config.json']
        editor = paths['config/editor/editor.json']
        self.apply('macos')
        fresh.write_bytes(b'{"theme":"personal"}\n')
        editor.write_bytes(b'{"schema":1,"backend":"external"}\n')
        self.apply('macos', force=True)
        self.assertEqual(fresh.read_bytes(), b'{"theme":"personal"}\n')
        self.assertEqual(editor.read_bytes(), b'{"schema":1,"backend":"external"}\n')

    def test_dev_edit_bridge_is_installed_on_unix_only(self):
        # The bridge is a POSIX shell wrapper: macOS and Linux get it, native
        # Windows needs a separate .cmd wrapper that is not qualified yet.
        for target in ('macos', 'linux'):
            paths, _ = config.config_targets(self.home, target)
            self.assertEqual(paths.get('config/bridge/dev-edit'), self.home / '.local/bin/dev-edit')
        windows, _ = config.config_targets(self.home, 'windows')
        self.assertNotIn('config/bridge/dev-edit', windows)

    def test_linux_bridge_routes_through_selected_python_and_runtime(self):
        # Regression: the bridge used to be macOS-only, so `fe` on Linux exited
        # 127. Prove a Linux apply installs an executable bridge that forwards
        # the literal arguments to the deployed runtime.
        deployed = self.base / "linux runtime ' % ! & (safe)"
        shutil.copytree(ROOT / 'config', deployed / 'config')
        (deployed / 'bootstrap').mkdir()
        (deployed / 'bootstrap/cockpit.py').write_text(
            'import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
        self.apply('linux', root=deployed, python_executable=sys.executable)
        bridge = self.home / '.local/bin/dev-edit'
        self.assertTrue(bridge.stat().st_mode & stat.S_IXUSR)
        argument = "file with spaces ' and\nnewline"
        result = subprocess.run([str(bridge), '--', argument], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['edit', '--', argument])

    def test_macos_fresh_config_ignores_xdg_like_fresh_does(self):
        # Verified against Fresh 0.5.1: `fresh --cmd config paths` reports
        # ~/.config/fresh on macOS even with XDG_CONFIG_HOME set, so writing to
        # the XDG location would install a file Fresh never reads.
        configured = self.base / 'xdg config'
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(configured)}):
            paths, _ = config.config_targets(self.home, 'macos', use_environment=True)
        self.assertEqual(paths['config/fresh/config.json'],
                         self.home / '.config/fresh/config.json')
        self.assertNotEqual(paths['config/fresh/config.json'].parent.parent, configured)

    def test_macos_fresh_config_uses_the_qualified_schema_version(self):
        # Fresh 0.5.1 reports and writes "version": 2; shipping version 1 would
        # be silently migrated and rewritten under the user.
        import json as _json
        declared = _json.loads((ROOT / 'config/fresh/config.json').read_text())
        self.assertEqual(declared['version'], 2)
        self.assertIs(declared['check_for_updates'], False)
        self.assertIs(declared['editor']['line_numbers'], True)

    def test_bridge_uses_selected_python_and_deployed_runtime(self):
        deployed = self.base / "deployed runtime ' % ! & (safe)"
        shutil.copytree(ROOT / 'config', deployed / 'config')
        (deployed / 'bootstrap').mkdir()
        (deployed / 'bootstrap/cockpit.py').write_text(
            'import json,sys\nprint(json.dumps(sys.argv[1:]))\n')
        selected_python = Path(sys.executable).resolve()
        self.apply('macos', root=deployed, python_executable=selected_python)
        bridge = self.home / '.local/bin/dev-edit'
        self.assertTrue(bridge.stat().st_mode & stat.S_IXUSR)
        argument = "file with spaces ' and\nnewline"
        result = subprocess.run([str(bridge), '--', argument], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['edit', '--', argument])
        text = bridge.read_text()
        self.assertIn(str(selected_python), text)
        self.assertIn(config.shlex.quote(str(deployed / 'bootstrap/cockpit.py')), text)

    def test_hammerspoon_bridge_is_default_on_macos_only(self):
        for target in ('linux', 'windows'):
            paths, _ = config.config_targets(self.home, target)
            self.assertNotIn('config/hammerspoon/init.lua', paths)
        default_macos, _ = config.config_targets(self.home, 'macos', profiles=['core', 'cockpit', 'terminal'])
        self.assertEqual(default_macos['config/hammerspoon/init.lua'], self.home / '.hammerspoon/init.lua')

    def test_default_macos_apply_installs_hammerspoon_bridge(self):
        self.home = self.base / 'gestures'
        self.apply('macos', profiles=['core', 'cockpit', 'terminal'])
        bridge = self.home / '.hammerspoon/init.lua'
        self.assertTrue(bridge.is_file())
        self.assertIn(b'hs.eventtap', bridge.read_bytes())
        contents = bridge.read_bytes()
        self.assertIn(b'"f1"', contents)
        self.assertIn(b'"f2"', contents)
        self.assertIn(b'"ctrl", "alt", "shift"', contents)

    def test_user_hammerspoon_init_is_preserved(self):
        self.home = self.base / 'hammerspoon-existing'
        existing = self.home / '.hammerspoon/init.lua'
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b'-- my own hammerspoon config\n')
        self.apply('macos', profiles=['core', 'cockpit', 'terminal'])
        self.assertEqual(existing.read_bytes(), b'-- my own hammerspoon config\n')

    def test_malformed_markers_fail_before_any_config_write(self):
        self.home.mkdir()
        profile = self.home / '.zshrc'
        profile.write_bytes(config.BEGIN + b'\n# no closing marker\n')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse((self.home / '.config/starship.toml').exists())
        self.assertFalse((self.home / '.config/dev-cockpit/init.sh').exists())
        self.assertFalse((self.home / '.bashrc').exists())

    def test_bad_ledger_fails_before_other_config_writes(self):
        _, ledger = config.config_targets(self.home, 'linux')
        ledger.parent.mkdir(parents=True)
        for value in ['not json', '[]', '{"schema":99,"files":{},"blocks":{}}', '{"schema":2,"files":{},"blocks":{"x":1}}']:
            ledger.write_text(value)
            with self.assertRaises(ValueError):
                self.apply()
            self.assertFalse((self.home / '.bashrc').exists())

    def test_legacy_ledger_migrates_without_adopting_unknown_files(self):
        paths, ledger = config.config_targets(self.home, 'linux')
        ledger.parent.mkdir(parents=True)
        owned = paths['config/starship/starship.toml']
        owned.write_bytes(b'# old managed default\n')
        private = self.home / 'private.txt'
        private.write_bytes(b'never delete')
        ledger.write_text(json.dumps({str(owned): config.digest(owned.read_bytes()), str(private): config.digest(private.read_bytes())}))
        self.apply()
        self.assertEqual(owned.read_bytes(), (ROOT / 'config/starship/starship.toml').read_bytes())
        self.apply(uninstall=True)
        self.assertEqual(private.read_bytes(), b'never delete')

    def test_symlinked_config_parent_rejected(self):
        self.home.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        try:
            (self.home / '.config').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation requires Windows Developer Mode')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_profile_preserved_and_setup_continues(self):
        # Issue #7: a stow/chezmoi managed ~/.bashrc must not abort setup.
        self.home.mkdir()
        outside = self.base / 'personal'
        outside.write_bytes(b'preserve')
        try:
            (self.home / '.bashrc').symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation requires Windows Developer Mode')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.apply(target='macos')
        self.assertTrue((self.home / '.bashrc').is_symlink())
        self.assertEqual(outside.read_bytes(), b'preserve')
        self.assertIn(config.BEGIN, (self.home / '.zshrc').read_bytes())
        self.assertTrue((self.home / '.config/dev-cockpit/starship.toml').is_file())
        self.assertIn('PRESERVE symlinked shell profile', output.getvalue())
        self.assertIn(config.BEGIN.decode(), output.getvalue())
        # Re-running (and uninstalling) stays non-fatal and never writes through.
        self.apply(target='macos')
        self.apply(target='macos', uninstall=True)
        self.assertEqual(outside.read_bytes(), b'preserve')

    def test_symlinked_profile_with_manual_block_is_not_reprinted(self):
        self.home.mkdir()
        outside = self.base / 'personal'
        outside.write_bytes(config.BEGIN + b"\n" + config.END + b"\n")
        try:
            (self.home / '.zshrc').symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation requires Windows Developer Mode')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.apply()
        self.assertNotIn('MANUAL', output.getvalue())

    def test_symlinked_config_file_preserved(self):
        self.home.mkdir()
        outside = self.base / 'bat-config'
        outside.write_bytes(b'mine')
        (self.home / '.config/bat').mkdir(parents=True)
        try:
            (self.home / '.config/bat/config').symlink_to(outside)
        except OSError:
            self.skipTest('Symlink creation requires Windows Developer Mode')
        self.apply()
        self.assertEqual(outside.read_bytes(), b'mine')
        self.assertTrue((self.home / '.config/dev-cockpit/starship.toml').is_file())
        statuses = {entry['path']: entry['status'] for entry in config.configuration_status(self.home, 'linux')}
        self.assertEqual(statuses[str((self.home / '.config/bat/config'))], 'symlinked')
        self.assertNotIn('error', statuses.values())

    def test_windows_reparse_point_rejected(self):
        class Junction:
            st_mode = stat.S_IFDIR
            st_file_attributes = 0x400
        with patch.object(Path, 'lstat', return_value=Junction()):
            with self.assertRaises(ValueError):
                config.reject_links(self.home)

    def test_profile_in_directory_named_like_shell_expansion(self):
        self.home = self.base / "a'b $(touch not-executed) `false` spaces"
        self.apply()
        self.assertIn("'\"'\"'", (self.home / '.bashrc').read_text())
        self.assertFalse((self.base / 'not-executed').exists())

    def test_existing_prompt_and_hooks_are_skipped(self):
        self.home.mkdir()
        (self.home / '.zshrc').write_text('source "$ZSH/oh-my-zsh.sh"\neval "$(zoxide init zsh)"\neval "$(atuin init zsh)"\n')
        self.apply()
        text = (self.home / '.zshrc').read_text()
        for name in ['STARSHIP', 'ZOXIDE', 'ATUIN']:
            self.assertIn('DEV_COCKPIT_SKIP_' + name + '=1', text)

    def test_powershell_companion_profile_prompt_is_respected(self):
        destination = self.home / 'Documents/PowerShell/Microsoft.PowerShell_profile.ps1'
        destination.parent.mkdir(parents=True)
        destination.write_text('oh-my-posh init pwsh | Invoke-Expression\n')
        self.apply('windows')
        managed = destination.parent / 'profile.ps1'
        self.assertIn("$env:DEV_COCKPIT_SKIP_STARSHIP = '1'", managed.read_text(encoding='utf-8-sig'))

    def test_utf16_powershell_profile_roundtrip_and_activation(self):
        for encoding in ['utf-16-le', 'utf-16-be']:
            self.home = self.base / encoding
            profile = self.home / 'Documents/PowerShell/profile.ps1'
            profile.parent.mkdir(parents=True)
            bom = b'\xff\xfe' if encoding == 'utf-16-le' else b'\xfe\xff'
            original = bom + '# personal café\r\n'.encode(encoding)
            profile.write_bytes(original)
            self.apply('windows')
            self.assertIn(config.BEGIN.decode(), profile.read_bytes()[2:].decode(encoding))
            self.apply('windows', uninstall=True)
            self.assertEqual(profile.read_bytes(), original)

    def test_existing_bash_login_profile_remains_selected(self):
        self.home.mkdir()
        (self.home / '.profile').write_text('# existing login\n')
        self.apply()
        self.assertIn(config.BEGIN, (self.home / '.profile').read_bytes())
        self.assertFalse((self.home / '.bash_profile').exists())

    def test_test_target_ignores_machine_environment(self):
        real = self.base / 'not test target'
        with patch.dict(os.environ, {'APPDATA': str(real), 'XDG_CONFIG_HOME': str(real), 'ZDOTDIR': str(real)}):
            self.apply('windows')
            self.apply('linux')
        self.assertFalse(real.exists())

    def test_environment_paths_must_be_absolute(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            with self.assertRaises(ValueError):
                config.config_targets(self.home, 'linux', use_environment=True)

    def test_concurrent_installer_lock_is_exclusive_and_released(self):
        directory = self.home / '.config/dev-cockpit'
        with config.configuration_lock(directory):
            with self.assertRaisesRegex(ValueError, 'locked'):
                self.apply()
        self.assertFalse((directory / 'configuration.lock').exists())
        self.apply()

    def test_lock_prevents_second_process(self):
        directory = self.home / 'state'
        with config.configuration_lock(directory):
            result = subprocess.run([sys.executable, '-c', 'from pathlib import Path; from dev_cockpit.configuration import configuration_lock; import sys\nwith configuration_lock(Path(sys.argv[1])): print("wrong")', str(directory)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('locked', result.stderr)

    def test_atomic_replace_failure_retains_original(self):
        self.home.mkdir()
        target = self.home / 'atomic.txt'
        target.write_bytes(b'original')
        with patch('dev_cockpit.configuration.os.replace', side_effect=PermissionError('read-only')):
            with self.assertRaises(PermissionError):
                config.atomic_write(target, b'replacement')
        self.assertEqual(target.read_bytes(), b'original')
        self.assertEqual(list(self.home.glob('.cockpit-*')), [])

    def test_doctor_reports_edited_block(self):
        self.apply()
        target = self.home / '.bashrc'
        target.write_bytes(b'# disabled\n')
        report = config.configuration_status(self.home, 'linux')
        self.assertEqual(next(item for item in report if item['path'] == str(target))['status'], 'edited')


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cockpit-completions ')
        self.home = Path(self.temp.name).resolve() / 'target'
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def fake_run(self, command, **kwargs):
        self.calls.append(command)
        output = 'example 1.2.3\n' if command[-1] == '--version' else '# generated shell completion\n'
        return subprocess.CompletedProcess(command, 0, stdout=output if kwargs.get('text') else output.encode())

    def test_only_installed_binaries_generate_and_second_run_uses_cache(self):
        with patch('dev_cockpit.configuration.shutil.which', side_effect=lambda name: '/bin/' + name if name in ['gh', 'omp'] else None), patch('dev_cockpit.configuration.subprocess.run', side_effect=self.fake_run):
            first = config.generate_completions(self.home, 'linux')
            self.assertEqual(sum(x['status'] == 'generated' for x in first), 4)
            self.calls.clear()
            second = config.generate_completions(self.home, 'linux')
            self.assertEqual(sum(x['status'] == 'cached' for x in second), 4)
            self.assertTrue(all(cmd[-1] == '--version' for cmd in self.calls))

    def test_changed_completion_is_preserved_even_with_force(self):
        with patch('dev_cockpit.configuration.shutil.which', side_effect=lambda name: '/bin/gh' if name == 'gh' else None), patch('dev_cockpit.configuration.subprocess.run', side_effect=self.fake_run):
            config.generate_completions(self.home, 'linux')
            target = self.home / '.config/dev-cockpit/completions/bash/gh.bash'
            target.write_bytes(b'# personal completion\n')
            report = config.generate_completions(self.home, 'linux', force=True)
            self.assertIn({'tool': 'gh', 'shell': 'bash', 'status': 'preserved'}, report)
            self.assertEqual(target.read_bytes(), b'# personal completion\n')

    def test_uninstall_removes_cached_completions_preserving_edits(self):
        with patch('dev_cockpit.configuration.shutil.which', side_effect=lambda name: '/bin/gh' if name == 'gh' else None), patch('dev_cockpit.configuration.subprocess.run', side_effect=self.fake_run):
            config.generate_completions(self.home, 'linux')
        bash = self.home / '.config/dev-cockpit/completions/bash/gh.bash'
        zsh = self.home / '.config/dev-cockpit/completions/zsh/_gh'
        bash.write_bytes(b'# personal changed completion')
        with contextlib.redirect_stdout(io.StringIO()):
            config.manage_config(self.home, 'linux', uninstall=True, apply=True)
        self.assertFalse(zsh.exists())
        self.assertEqual(bash.read_bytes(), b'# personal changed completion')

    def test_omp_powershell_is_reported_unsupported(self):
        with patch('dev_cockpit.configuration.shutil.which', side_effect=lambda name: '/bin/omp' if name == 'omp' else None), patch('dev_cockpit.configuration.subprocess.run', side_effect=self.fake_run):
            report = config.generate_completions(self.home, 'windows')
        self.assertIn({'tool': 'omp', 'shell': 'powershell', 'status': 'unsupported'}, report)
        self.assertEqual(len(self.calls), 1)

    def test_optional_generator_failure_is_reported(self):
        with patch('dev_cockpit.configuration.shutil.which', return_value='/bin/fake'), patch('dev_cockpit.configuration.subprocess.run', side_effect=subprocess.TimeoutExpired('fake', 1)):
            report = config.generate_completions(self.home, 'linux')
        self.assertTrue(all(item['status'] == 'unavailable' for item in report))


if __name__ == '__main__':
    unittest.main()
