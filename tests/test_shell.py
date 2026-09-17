"""Execute profile integration in real, isolated shells without changing HOME."""
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from dev_cockpit import configuration as config

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['starship', 'zoxide', 'fzf', 'atuin', 'mise', 'direnv', 'eza', 'lazygit', 'delta', 'yazi', 'fd']


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit-shell ' quotes ")
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "profile home ' $(not-executed)"
        self.checkout = self.base / "runtime ' checkout"
        shutil.copytree(ROOT / 'config', self.checkout / 'config')
        (self.checkout / 'bootstrap').mkdir()
        (self.checkout / 'bootstrap/cockpit.py').write_text('import json,sys\nprint("ARGUMENTS=" + json.dumps(sys.argv[1:]))\n')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.log = self.base / 'tools.log'
        for name in TOOLS:
            path = self.bin / name
            path.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$DEV_COCKPIT_TEST_LOG"\nprintf ":\\n"\n')
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + '/usr/bin:/bin', DEV_COCKPIT_TEST_LOG=str(self.log),
                        XDG_CONFIG_HOME=str(self.home / '.config'), HISTFILE=str(self.base / 'history'),
                        DEV_COCKPIT_SKIP_SUGGESTIONS='1', DEV_COCKPIT_SKIP_HIGHLIGHTING='1')
        for key in ['DEV_COCKPIT_INITIALIZED', 'STARSHIP_SESSION_KEY', 'STARSHIP_CONFIG', 'ZDOTDIR', 'BASH_ENV', 'ENV']:
            self.env.pop(key, None)
        for name in ['STARSHIP', 'ATUIN', 'ZOXIDE', 'MISE', 'DIRENV', 'FZF']:
            self.env.pop('DEV_COCKPIT_SKIP_' + name, None)
        with contextlib.redirect_stdout(io.StringIO()):
            config.manage_config(self.home, 'linux', apply=True, root=self.checkout, python_executable=sys.executable)

    def tearDown(self):
        self.temp.cleanup()

    def run_shell(self, shell, source, after='', before=''):
        executable = shutil.which(shell)
        if not executable:
            self.skipTest(shell + ' unavailable on this runner')
        flags = ['--noprofile', '--norc', '-i', '-c'] if shell == 'bash' else ['-d', '-f', '-i', '-c']
        command = before + '\n. ' + shlex.quote(str(source)) + '\n' + after
        return subprocess.run([executable, *flags, command], cwd=self.base, env=self.env, capture_output=True, text=True, timeout=30)

    def test_bash_and_zsh_activate_each_hook_once_and_quote_arguments(self):
        for shell in ['bash', 'zsh']:
            if not shutil.which(shell):
                continue
            self.log.unlink(missing_ok=True)
            profile = self.home / ('.bashrc' if shell == 'bash' else '.zshrc')
            result = self.run_shell(shell, profile, '. ' + shlex.quote(str(profile)) + '\ndev "project with spaces" "quote\x27s"')
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads(next(line.removeprefix('ARGUMENTS=') for line in result.stdout.splitlines() if line.startswith('ARGUMENTS=')))
            self.assertEqual(arguments, ['launch', 'project with spaces', "quote's"])
            calls = self.log.read_text().splitlines()
            for name in ['starship', 'zoxide', 'fzf', 'atuin', 'mise', 'direnv']:
                self.assertEqual(sum(line.startswith(name + ' ') for line in calls), 1, calls)
            self.assertFalse((self.base / 'not-executed').exists())

    def test_user_alias_and_function_names_are_preserved(self):
        for shell in ['bash', 'zsh']:
            if not shutil.which(shell):
                continue
            profile = self.home / ('.bashrc' if shell == 'bash' else '.zshrc')
            result = self.run_shell(shell, profile, 'eval dev\ndev-doctor', before="alias dev='printf personal-alias'\nfunction dev-doctor { printf personal-function; }")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('personal-alias', result.stdout)
            self.assertIn('personal-function', result.stdout)
            self.assertNotIn('ARGUMENTS=', result.stdout)

    @unittest.skipIf(os.name == 'nt', 'POSIX dash sourcing is not meaningful under MSYS path conventions; Windows shell integration is PowerShell (covered by the nt-gated test)')
    def test_interactive_posix_shell_ignores_bash_zsh_integration(self):
        executable = shutil.which('dash')
        if not executable:
            self.skipTest('dash unavailable')
        script = self.home / '.config/dev-cockpit/init.sh'
        env = dict(self.env, DEV_COCKPIT_CONFIG_DIR=str(script.parent))
        result = subprocess.run([executable, '-i', '-c', '. ' + shlex.quote(str(script)) + '; printf shell-survived'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shell-survived', result.stdout)
        self.assertFalse(self.log.exists())

    def test_noninteractive_bash_does_nothing(self):
        executable = shutil.which('bash')
        if not executable:
            self.skipTest('bash unavailable')
        script = self.home / '.config/dev-cockpit/init.sh'
        result = subprocess.run([executable, '--noprofile', '--norc', '-c', '. ' + shlex.quote(str(script)) + '; type dev'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_nonzero_optional_hook_does_not_break_shell(self):
        for name in ['starship', 'zoxide', 'fzf', 'atuin', 'mise', 'direnv']:
            (self.bin / name).write_text('#!/bin/sh\nexit 17\n')
        for shell in ['bash', 'zsh']:
            if not shutil.which(shell):
                continue
            result = self.run_shell(shell, self.home / ('.bashrc' if shell == 'bash' else '.zshrc'), 'dev-doctor')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ARGUMENTS=["doctor"]', result.stdout)

    def test_preserves_user_starship_and_fzf_settings(self):
        self.env['STARSHIP_CONFIG'] = str(self.base / 'personal prompt.toml')
        self.env['FZF_DEFAULT_OPTS'] = '--height=25%'
        self.env['FZF_CTRL_T_COMMAND'] = ''
        result = self.run_shell('bash', self.home / '.bashrc', 'printf "PROMPT=%s\\nFZF=%s\\nCTRLT=%s\\n" "$STARSHIP_CONFIG" "$FZF_DEFAULT_OPTS" "$FZF_CTRL_T_COMMAND"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PROMPT=' + self.env['STARSHIP_CONFIG'], result.stdout)
        self.assertIn('FZF=--height=25%', result.stdout)
        self.assertIn('CTRLT=\n', result.stdout)

    @unittest.skipIf(os.name == 'nt', 'The yazi cd helper is a POSIX shell feature; Windows shell integration is PowerShell (covered by the nt-gated test)')
    def test_yazi_helper_changes_current_shell_directory(self):
        destination = self.base / "selected directory ' quote"
        destination.mkdir()
        script = '#!/bin/sh\nfor argument do\ncase "$argument" in --cwd-file=*) printf "%s" "$DEV_COCKPIT_TEST_CWD" > "${argument#--cwd-file=}" ;; esac\ndone\n'
        (self.bin / 'yazi').write_text(script)
        self.env['DEV_COCKPIT_TEST_CWD'] = str(destination)
        result = self.run_shell('bash', self.home / '.bashrc', 'y; printf "DIRECTORY=%s\\n" "$PWD"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DIRECTORY=' + str(destination), result.stdout)

    def test_shell_wrappers_forward_all_cli_commands(self):
        result = self.run_shell('bash', self.home / '.bashrc', '\n'.join(name + ' "--some flag"' for name in ['dev-doctor', 'dev-update', 'dev-uninstall', 'dev-memory', 'dev-graph', 'dev-completions']))
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = [json.loads(line.removeprefix('ARGUMENTS=')) for line in result.stdout.splitlines() if line.startswith('ARGUMENTS=')]
        self.assertEqual(actual, [[name, '--some flag'] for name in ['doctor', 'update', 'uninstall', 'memory', 'graph', 'completions']])

    @unittest.skipUnless(os.name == 'nt', 'Native Windows profile execution runs in Windows CI')
    def test_native_powershell_profiles_parse_and_forward_arguments(self):
        for shell in ['powershell', 'pwsh']:
            executable = shutil.which(shell)
            if not executable:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                config.manage_config(self.home, 'windows', apply=True, root=self.checkout, python_executable=sys.executable)
            profile = self.home / 'Documents/PowerShell/profile.ps1'
            entry = self.base / ('entry-' + shell + '.ps1')
            # Explicit tool-specific overrides isolate every optional hook.
            skips = '\n'.join("$env:DEV_COCKPIT_SKIP_" + name + "='1'" for name in ['STARSHIP', 'ZOXIDE', 'MISE', 'ATUIN', 'PSREADLINE'])
            entry.write_text(skips + '\n. ' + config._quote_ps(profile) + "\n. " + config._quote_ps(profile) + "\ndev 'project with spaces' 'quote''s'\n", encoding='utf-8-sig')
            result = subprocess.run([executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(entry)], cwd=self.base, env=os.environ.copy(), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ARGUMENTS=["launch", "project with spaces", "quote\'s"]', result.stdout)


if __name__ == '__main__':
    unittest.main()
