import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cockpit", ROOT / "bootstrap/cockpit.py")
cockpit = importlib.util.module_from_spec(spec)
sys.modules["cockpit"] = cockpit
spec.loader.exec_module(cockpit)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit tests ' with spaces ")
        self.home = Path(self.temp.name).resolve() / "test home"
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.temp.cleanup()

    def test_preview_does_not_create_home(self):
        for target in ["macos", "linux", "windows"]:
            cockpit.manage_config(self.home, target)
        self.assertFalse(self.home.exists())

    def test_apply_twice_is_idempotent_on_each_platform(self):
        for target in ["macos", "linux", "windows"]:
            home = self.home / target
            cockpit.manage_config(home, target, apply=True)
            before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob("*") if p.is_file()}
            self.assertEqual(cockpit.manage_config(home, target, apply=True), [])
            after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in home.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_existing_file_is_not_adopted_or_removed(self):
        paths, ledger = cockpit.config_targets(self.home, "linux")
        target = paths["config/herdr/config.toml"]
        target.parent.mkdir(parents=True)
        original = b'# personal config\n'
        target.write_bytes(original)
        cockpit.manage_config(self.home, "linux", apply=True)
        self.assertNotIn(str(target), json.loads(ledger.read_text()))
        cockpit.manage_config(self.home, "linux", apply=True, uninstall=True)
        self.assertEqual(target.read_bytes(), original)

    def test_user_edit_survives_apply_and_uninstall(self):
        cockpit.manage_config(self.home, "windows", apply=True)
        paths, _ = cockpit.config_targets(self.home, "windows")
        edited = paths["config/terminals/wezterm.lua"]
        edited.write_text("return { font_size = 16 }\n")
        cockpit.manage_config(self.home, "windows", apply=True)
        cockpit.manage_config(self.home, "windows", apply=True, uninstall=True)
        self.assertEqual(edited.read_text(), "return { font_size = 16 }\n")
        self.assertFalse(paths["config/herdr/config.toml"].exists())

    def test_uninstall_preview_is_read_only(self):
        cockpit.manage_config(self.home, "linux", apply=True)
        paths, ledger = cockpit.config_targets(self.home, "linux")
        before = ledger.read_bytes()
        cockpit.manage_config(self.home, "linux", uninstall=True)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertTrue(all(p.exists() for p in paths.values()))

    def test_changed_repository_config_updates_only_owned_file(self):
        cockpit.manage_config(self.home, "linux", apply=True)
        paths, ledger = cockpit.config_targets(self.home, "linux")
        target = paths["config/herdr/config.toml"]
        target.write_bytes(b"old version\n")
        state = json.loads(ledger.read_text())
        state[str(target)] = cockpit.digest(target.read_bytes())
        ledger.write_text(json.dumps(state))
        cockpit.manage_config(self.home, "linux", apply=True)
        self.assertEqual(target.read_bytes(), (ROOT / "config/herdr/config.toml").read_bytes())

    def test_invalid_ledger_fails_before_config_writes(self):
        paths, ledger = cockpit.config_targets(self.home, "linux")
        ledger.parent.mkdir(parents=True)
        ledger.write_text("bad json")
        with self.assertRaises(ValueError):
            cockpit.manage_config(self.home, "linux", apply=True)
        self.assertTrue(all(not p.exists() for p in paths.values()))

    def test_ledger_cannot_remove_arbitrary_files(self):
        _, ledger = cockpit.config_targets(self.home, "linux")
        ledger.parent.mkdir(parents=True)
        personal = self.home / "important.txt"
        personal.write_bytes(b"keep")
        ledger.write_text(json.dumps({str(personal): cockpit.digest(b"keep")}))
        cockpit.manage_config(self.home, "linux", apply=True, uninstall=True)
        self.assertEqual(personal.read_bytes(), b"keep")

    def test_symlinked_parent_is_rejected(self):
        self.home.mkdir(parents=True)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        try:
            (self.home / ".config").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation requires Windows developer mode or privileges")
        with self.assertRaises(ValueError):
            cockpit.manage_config(self.home, "linux", apply=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_test_home_ignores_real_appdata(self):
        with patch.dict(os.environ, {"APPDATA": str(Path(self.temp.name) / "real"), "XDG_CONFIG_HOME": str(Path(self.temp.name) / "real")}):
            cockpit.manage_config(self.home, "windows", apply=True)
        self.assertFalse((Path(self.temp.name) / "real").exists())

    def test_profiles_and_ssh_are_never_modified(self):
        self.home.mkdir(parents=True)
        for name in [".zshrc", ".bashrc", ".gitconfig"]:
            (self.home / name).write_text("personal\n")
        cockpit.manage_config(self.home, "macos", apply=True)
        for name in [".zshrc", ".bashrc", ".gitconfig"]:
            self.assertEqual((self.home / name).read_text(), "personal\n")
        self.assertFalse((self.home / ".ssh").exists())


class PackageTests(unittest.TestCase):
    def test_windows_uses_native_winget(self):
        plan = cockpit.package_plan("windows", ["core"])
        self.assertEqual(len(plan), 11)
        self.assertTrue(all(command[0] == "winget" for _, command, _ in plan))
        self.assertFalse(any("bash" in command for _, command, _ in plan))

    def test_terminal_choices_match_owner(self):
        self.assertEqual([t[0]["id"] for t in cockpit.package_plan("macos", ["terminal"])], ["ghostty"])
        self.assertEqual([t[0]["id"] for t in cockpit.package_plan("windows", ["terminal"])], ["wezterm"])

    @patch("cockpit.subprocess.run")
    @patch("cockpit.shutil.which", return_value=None)
    def test_preview_executes_no_package_commands(self, which, run):
        with contextlib.redirect_stdout(io.StringIO()):
            cockpit.run_packages(cockpit.package_plan("linux", ["core"]))
        run.assert_not_called()

    @patch("cockpit.subprocess.run")
    @patch("cockpit.shutil.which", return_value=None)
    def test_manual_adapter_stops_before_any_install(self, which, run):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            cockpit.run_packages(cockpit.package_plan("windows", ["core", "cockpit"]), install=True)
        run.assert_not_called()

    @patch("cockpit.subprocess.run", side_effect=subprocess.CalledProcessError(7, ["brew"]))
    @patch("cockpit.shutil.which", side_effect=lambda name: "/bin/brew" if name == "brew" else None)
    def test_package_failure_is_propagated(self, which, run):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
            cockpit.run_packages(cockpit.package_plan("linux", ["core"]), install=True)
        self.assertEqual(run.call_count, 1)

    def test_mutation_cannot_be_hidden_by_dry_run(self):
        result = subprocess.run([sys.executable, str(ROOT / "bootstrap/cockpit.py"), "--dry-run", "--install"], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_config_home_is_not_a_package_sandbox(self):
        result = subprocess.run([sys.executable, str(ROOT / "bootstrap/cockpit.py"), "--install", "--home", "dummy"], capture_output=True)
        self.assertEqual(result.returncode, 2)


class AssetTests(unittest.TestCase):
    def test_toml_assets_parse(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("TOML parsing validation requires Python 3.11+")
        for path in (ROOT / "config").rglob("*.toml"):
            with path.open("rb") as stream:
                self.assertIsInstance(tomllib.load(stream), dict)

    def test_vendored_assets_have_pinned_sources(self):
        for asset in json.loads((ROOT / "licenses/sources.json").read_text()):
            self.assertRegex(asset["revision"], r"^[0-9a-f]{40}$")
            self.assertTrue((ROOT / asset["file"]).is_file())
            self.assertEqual(hashlib.sha256((ROOT / asset["file"]).read_bytes()).hexdigest(), asset["sha256"])


if __name__ == "__main__":
    unittest.main()
