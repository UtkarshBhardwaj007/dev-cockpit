"""Unified CLI (dev_cockpit.cli) and bootstrap shim coverage."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dev_cockpit import cli  # noqa: E402


def run(argv, home):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--home", str(home), *argv])
    return code, out.getvalue()


class CliSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit cli ' ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"

    def test_preview_is_read_only_on_all_platforms(self):
        for target in ("macos", "linux", "windows"):
            code, out = run(["--platform", target, "--profile", "core"], self.home)
            self.assertEqual(code, 0, out)
            self.assertIn("preview", out)
            self.assertFalse(self.home.exists())

    def test_doctor_returns_integer_and_reports_tools(self):
        # The assertion is about doctor output shape, not whatever happens to
        # be installed on the machine running the suite.
        def deterministic_doctor(*_args, **_kwargs):
            print("FOUND present-tool /fixture")
            print("MISSING absent-tool")
            return 1

        with unittest.mock.patch("dev_cockpit.cli.packages.doctor", side_effect=deterministic_doctor) as doctor:
            code, out = run(["--doctor", "--profile", "core"], self.home)
        self.assertIsInstance(code, int)
        self.assertIn("FOUND", out)
        self.assertIn("MISSING", out)
        doctor.assert_called_once()

    def test_profile_choices_are_validated(self):
        for profile in ("bogus", "gestures"):
            with self.assertRaises(SystemExit):
                run(["--profile", profile], self.home)

    def test_dry_run_and_mutation_conflict(self):
        with self.assertRaises(SystemExit):
            run(["--dry-run", "--install"], self.home)

    def test_cross_platform_mutation_is_preview_only(self):
        with self.assertRaises(SystemExit):
            run(["--platform", "linux", "--install"], self.home)

    def test_home_cannot_sandbox_installation(self):
        with self.assertRaises(SystemExit):
            run(["--home", str(self.home), "--install"], self.home)

    def test_uninstall_conflicts_with_install(self):
        with self.assertRaises(SystemExit):
            run(["--uninstall-config", "--install"], self.home)

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.configuration.generate_completions", return_value=[])
    def test_setup_install_generates_completions(self, gen, run):
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            code = cli._setup(["--install"])
            gen.assert_called_with(Path.home(), cli.host_platform(), use_environment=True, force=False)
        self.assertEqual(code, 0)
        run.assert_called_once()
        gen.assert_called_once()

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.configuration.generate_completions", return_value=[])
    def test_setup_apply_config_does_not_generate_completions(self, gen, run):
        code = cli._setup(["--apply-config", "--home", str(self.home)])
        self.assertEqual(code, 0)
        gen.assert_not_called()

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.configuration.generate_completions", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.packages.launch_gesture_bridge", return_value=None)
    def test_setup_install_starts_default_gesture_bridge(self, launch, gen, run):
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home):
            cli._setup(["--install"])
        launch.assert_called_once_with(cli.host_platform(), home=self.home)

    @unittest.mock.patch("dev_cockpit.cli.packages.launch_gesture_bridge", return_value="launched Hammerspoon")
    def test_gesture_bridge_helper_prints_accessibility_reminder(self, launch):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._launch_gesture_bridge("macos", self.home)
        text = out.getvalue()
        self.assertIn("Accessibility", text)
        # Reload Config reloads Lua but does not restart the process, so it does
        # not pick up a freshly granted Accessibility permission.
        self.assertIn("quit and reopen Hammerspoon", text)

    @unittest.mock.patch("dev_cockpit.cli.packages.launch_gesture_bridge", return_value=None)
    def test_gesture_bridge_helper_is_quiet_when_not_applicable(self, launch):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli._launch_gesture_bridge("linux", self.home)
        self.assertEqual(out.getvalue(), "")

    def test_subcommands_dispatch_mobile(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["mobile"])
        self.assertEqual(code, 0)
        self.assertIn("Mobile access", out.getvalue())

    def test_intelligence_subcommands_parse(self):
        # graph/memory require live tools; just ensure dispatch reaches its parser.
        code = cli.main(["graph", "doctor", ".", "--home", str(self.home)])
        self.assertIn(code, (0, 1))


class RuntimeDeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit runtime ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"

    def _install(self, deploy_env=False):
        env = {"HOME": str(self.home)}
        if deploy_env:
            env["DEV_COCKPIT_DEPLOY_RUNTIME"] = "1"

        @contextlib.contextmanager
        def _patched_env():
            with unittest.mock.patch.dict(os.environ, env):
                os.environ.pop("XDG_CONFIG_HOME", None)
                os.environ.pop("APPDATA", None)
                yield

        return _patched_env()

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.runtime.deploy_runtime")
    def test_install_with_deploy_env_deploys_runtime(self, deploy, run):
        # Return the real repo root so package_plan/manage_config can read
        # manifests/config; this mirrors the persistent copy deploy_runtime makes.
        deploy.return_value = ROOT
        with self._install(deploy_env=True):
            code = cli._setup(["--install", "--apply-config"])
            target = cli.host_platform()
            home = Path.home() if target == "windows" else self.home
            _, ledger = cli.configuration.config_targets(home, target, use_environment=True)
            env_name = "environment.ps1" if target == "windows" else "environment.sh"
            env = (ledger.parent / env_name).read_text()
        self.assertEqual(code, 0)
        deploy.assert_called_once()
        if target == "windows":
            self.assertIn("$env:DEV_COCKPIT_ROOT = " + cli.configuration._quote_ps(str(ROOT)), env)
        else:
            self.assertIn("DEV_COCKPIT_ROOT=" + str(ROOT), env)

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.runtime.deploy_runtime")
    def test_install_without_deploy_env_does_not_deploy(self, deploy, run):
        with self._install(deploy_env=False):
            code = cli._setup(["--install", "--apply-config"])
        self.assertEqual(code, 0)
        deploy.assert_not_called()

    @unittest.mock.patch("dev_cockpit.cli.runtime.deploy_runtime")
    def test_deploy_only_when_installing(self, deploy):
        with self._install(deploy_env=True):
            code = cli._setup(["--apply-config"])
        self.assertEqual(code, 0)
        deploy.assert_not_called()


class ShimTests(unittest.TestCase):
    def test_bootstrap_shim_forwards_to_cli(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bootstrap/cockpit.py"), "--platform", "linux", "--profile", "core"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dev Cockpit | linux | core | preview", result.stdout)


class VendoredAssetTests(unittest.TestCase):
    def test_vendored_assets_have_pinned_sources(self):
        for asset in json.loads((ROOT / "licenses/sources.json").read_text()):
            self.assertRegex(asset["revision"], r"^[0-9a-f]{40}$")
            self.assertTrue((ROOT / asset["file"]).is_file())
            self.assertEqual(hashlib.sha256((ROOT / asset["file"]).read_bytes()).hexdigest(), asset["sha256"])


if __name__ == "__main__":
    unittest.main()


class SubcommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit subcmd ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"

    def test_doctor_subcommand_reports_tools_and_config(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["doctor", "--home", str(self.home)])
        self.assertIsInstance(code, int)
        text = out.getvalue()
        self.assertIn("FOUND", text)
        self.assertIn("CONFIG", text)

    @unittest.mock.patch("dev_cockpit.cli.packages.gesture_bridge_app", return_value=Path("/Applications/Hammerspoon.app"))
    def test_doctor_default_reports_hammerspoon_on_macos(self, app):
        if cli.host_platform() != "macos":
            self.skipTest("Hammerspoon is macOS-only")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["doctor", "--home", str(self.home)])
        text = out.getvalue()
        self.assertIn("GESTURE", text)
        self.assertIn("Hammerspoon.app", text)
        self.assertIn("Accessibility", text)

    def test_uninstall_dry_run_is_read_only(self):
        cli.main(["--home", str(self.home), "--apply-config"])
        paths, _ = cli.configuration.config_targets(self.home, cli.host_platform())
        target = paths["config/starship/starship.toml"]
        self.assertTrue(target.exists())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["uninstall", "--home", str(self.home), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(target.exists())

    def test_uninstall_removes_owned_files(self):
        cli.main(["--home", str(self.home), "--apply-config"])
        paths, _ = cli.configuration.config_targets(self.home, cli.host_platform())
        target = paths["config/starship/starship.toml"]
        self.assertTrue(target.exists())
        code = cli.main(["uninstall", "--home", str(self.home)])
        self.assertEqual(code, 0)
        self.assertFalse(target.exists())

    def test_completions_subcommand_runs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["completions", "--home", str(self.home)])
        self.assertEqual(code, 0)

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    @unittest.mock.patch("dev_cockpit.cli.configuration.generate_completions", return_value=[])
    def test_update_runs_config_completions_and_packages(self, gen, run):
        code = cli.main(["update", "--home", str(self.home)])
        self.assertEqual(code, 0)
        run.assert_called_once()
        gen.assert_called_once()

    @unittest.mock.patch("dev_cockpit.cli.packages.run_packages", return_value=[])
    def test_force_config_flag_is_accepted(self, run):
        code = cli.main(["--apply-config", "--force-config", "--home", str(self.home)])
        self.assertEqual(code, 0)

    @unittest.mock.patch("dev_cockpit.workspace.launch", return_value=0)
    def test_open_subcommand_launches_workspace(self, launch):
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            code = cli.main(["open", "."])
        self.assertEqual(code, 0)
        launch.assert_called_once()
        self.assertEqual(launch.call_args[0][0], Path(".").resolve())

    @unittest.mock.patch("dev_cockpit.workspace.launch", return_value=0)
    def test_open_defaults_to_current_directory(self, launch):
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            code = cli.main(["open"])
        self.assertEqual(code, 0)
        launch.assert_called_once()
        self.assertEqual(launch.call_args[0][0], Path.cwd().resolve())

    @unittest.mock.patch("dev_cockpit.workspace.launch", return_value=0)
    def test_open_code_layout_uses_named_fresh_session(self, launch):
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home), \
                unittest.mock.patch("dev_cockpit.cli.host_platform", return_value="macos"), \
                unittest.mock.patch("dev_cockpit.editor.code_layout_support",
                                    return_value=(True, "")):
            code = cli.main(["open", ".", "--layout", "code"])
        self.assertEqual(code, 0)
        self.assertEqual(launch.call_args.kwargs["layout"], "code")
        self.assertEqual(launch.call_args.kwargs["editor_command"][:2], ["fresh", "-a"])

    @unittest.mock.patch("dev_cockpit.workspace.launch", return_value=0)
    def test_open_code_layout_keeps_classic_when_editor_is_unavailable(self, launch):
        # An unqualified platform (or a missing Fresh binary) must not activate a
        # layout whose editor pane cannot run, and must not silently substitute a
        # different editor.
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home), \
                unittest.mock.patch("dev_cockpit.cli.host_platform", return_value="linux"):
            out = io.StringIO()
            with contextlib.redirect_stderr(out):
                code = cli.main(["open", ".", "--layout", "code"])
        self.assertEqual(code, 0)
        self.assertEqual(launch.call_args.kwargs["layout"], "classic")
        self.assertIsNone(launch.call_args.kwargs["editor_command"])
        self.assertIn("CODE LAYOUT UNAVAILABLE", out.getvalue())
        self.assertIn("classic layout", out.getvalue())

    @unittest.mock.patch("dev_cockpit.editor.open_files", return_value=7)
    def test_edit_subcommand_normalizes_literal_file_arguments(self, open_files):
        file = self.home / "project/file with & quote'.py"
        file.parent.mkdir(parents=True)
        file.write_text("pass\n")
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home):
            code = cli.main(["edit", "--project", str(file.parent), "--", str(file)])
        self.assertEqual(code, 7)
        request = open_files.call_args.args[0]
        self.assertEqual(request.files, (file.resolve(),))
        self.assertEqual(request.project, file.parent.resolve())

    @unittest.mock.patch("dev_cockpit.workspace.focus_project_tab", return_value={"created": True})
    def test_files_and_review_use_dedicated_tabs(self, focus):
        project = self.home / "project"
        project.mkdir(parents=True)
        self.assertEqual(cli.main(["files", str(project)]), {"created": True})
        self.assertEqual(focus.call_args.args[1], "Files")
        self.assertEqual(cli.main(["review", str(project)]), {"created": True})
        self.assertEqual(focus.call_args.args[1], "Review")

    @unittest.mock.patch("dev_cockpit.editor.language_pack_status", return_value=[])
    @unittest.mock.patch("dev_cockpit.editor.resolve_editor_settings")
    def test_editor_languages_list_is_read_only(self, settings, status):
        from dev_cockpit.editor import EditorSettings
        settings.return_value = EditorSettings()
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home):
            self.assertEqual(cli.main(["editor", "languages", "list"]), 0)
        status.assert_called_once()

    def test_editor_language_install_fails_before_unqualified_changes(self):
        from dev_cockpit.editor import EditorError
        with unittest.mock.patch("dev_cockpit.cli.Path.home", return_value=self.home):
            with self.assertRaisesRegex(EditorError, "not yet qualified"):
                cli.main(["editor", "languages", "install", "javascript", "go"])
