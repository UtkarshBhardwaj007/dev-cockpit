"""Execute public launchers against an isolated recorder, never install packages."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit launcher ' ")
        self.addCleanup(self.temp.cleanup)
        self.bootstrap = Path(self.temp.name) / 'bootstrap'
        self.bootstrap.mkdir()
        (self.bootstrap / 'cockpit.py').write_text('import json,sys\nprint("RECORDER="+json.dumps(sys.argv[1:]))\n')
        for name in ('setup.sh', 'setup.ps1'):
            shutil.copyfile(ROOT / 'bootstrap' / name, self.bootstrap / name)

    def recorded(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = next(x for x in result.stdout.splitlines() if x.startswith('RECORDER='))
        return json.loads(line.removeprefix('RECORDER='))

    @unittest.skipIf(os.name == 'nt', 'Native Unix launcher')
    def test_unix_defaults_to_install_and_configure(self):
        result = subprocess.run(['sh', str(self.bootstrap / 'setup.sh')], text=True, capture_output=True)
        self.assertEqual(self.recorded(result), ['--install', '--apply-config'])

    @unittest.skipIf(os.name == 'nt', 'Native Unix launcher')
    def test_unix_dry_run_and_space_arguments_are_preserved(self):
        args = ['--dry-run', '--home', str(Path(self.temp.name) / "personal home '"), '--profile', 'core']
        result = subprocess.run(['sh', str(self.bootstrap / 'setup.sh'), *args], text=True, capture_output=True)
        self.assertEqual(self.recorded(result), args)
        self.assertFalse((Path(self.temp.name) / "personal home '").exists())

    @unittest.skipIf(os.name == 'nt', 'Native Unix launcher')
    def test_unix_action_flag_does_not_silently_install(self):
        result = subprocess.run(['sh', str(self.bootstrap / 'setup.sh'), '--apply-config'], text=True, capture_output=True)
        self.assertEqual(self.recorded(result), ['--apply-config'])

    def test_powershell_dry_run_mapping_and_quoting(self):
        shell = shutil.which('pwsh') or (shutil.which('powershell') if os.name == 'nt' else None)
        if not shell:
            self.skipTest('PowerShell available in native Windows CI')
        env = dict(os.environ)
        for name, fallback in [('USERPROFILE', str(Path.home())), ('LOCALAPPDATA', str(Path(self.temp.name) / 'local')), ('ProgramFiles', str(Path(self.temp.name) / 'programs'))]:
            env.setdefault(name, fallback)
        args = ['-NoProfile', '-File', str(self.bootstrap / 'setup.ps1'), '-DryRun', '-HomeDirectory', str(Path(self.temp.name) / "personal home '")]
        result = subprocess.run([shell, *args], text=True, capture_output=True, env=env)
        self.assertEqual(self.recorded(result), ['--dry-run', '--home', str(Path(self.temp.name) / "personal home '")])


if __name__ == '__main__':
    unittest.main()
