import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from dev_cockpit.editor import (
    EditorError,
    EditorRequest,
    EditorSettings,
    RoutingUnavailable,
    build_editor_command,
    build_editor_pane_command,
    canonical_language_packs,
    code_layout_support,
    describe_editor_substitution,
    doctor_editor,
    editor_settings_path,
    effective_editor_settings,
    fresh_qualified,
    language_pack_status,
    normalize_edit_paths,
    open_files,
    project_identity,
    resolve_editor_settings,
    validate_editor_settings,
    validate_location,
)


class EditorSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="editor settings '")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"

    def test_missing_settings_use_safe_defaults(self):
        self.assertEqual(resolve_editor_settings(self.home, "linux"), EditorSettings())
        self.assertFalse(self.home.exists())

    def test_platform_paths_and_explicit_environment(self):
        self.assertEqual(editor_settings_path(self.home, "linux"),
                         self.home.resolve() / ".config/dev-cockpit/editor.json")
        self.assertEqual(editor_settings_path(self.home, "windows"),
                         self.home.resolve() / "AppData/Roaming/dev-cockpit/editor.json")
        custom = self.home.resolve() / "custom config"
        self.assertEqual(editor_settings_path(self.home, "macos", {"XDG_CONFIG_HOME": str(custom)}),
                         custom / "dev-cockpit/editor.json")
        with self.assertRaisesRegex(EditorError, "must be absolute"):
            editor_settings_path(self.home, "windows", {"APPDATA": "relative"})

    def test_environment_is_not_implicitly_inherited(self):
        service = self.home.resolve() / "service-profile"
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(service)}):
            self.assertNotEqual(editor_settings_path(self.home, "linux").parent.parent, service)

    def test_loads_external_argv_without_splitting_spaces(self):
        path = editor_settings_path(self.home, "linux")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "schema": 1,
            "backend": "external",
            "external_command": ["/Applications/My Editor/editor", "--reuse-window"],
            "external_wait_command": ["/Applications/My Editor/editor", "--wait"],
            "language_packs": ["javascript", "go"],
        }), encoding="utf-8")
        settings = resolve_editor_settings(self.home, "linux")
        self.assertEqual(settings.external_command[0], "/Applications/My Editor/editor")
        self.assertEqual(settings.language_packs, ("typescript", "go"))

    def test_schema_is_strict(self):
        baseline = {
            "schema": 1, "backend": "fresh", "external_command": None,
            "external_wait_command": None, "language_packs": [],
        }
        invalid = [
            dict(baseline, schema=True),
            dict(baseline, schema=2),
            dict(baseline, backend="vim"),
            dict(baseline, surprise=True),
            dict(baseline, external_command="code --wait"),
            dict(baseline, external_command=[]),
            dict(baseline, external_command=["code", ""]),
            dict(baseline, language_packs="go"),
            dict(baseline, language_packs=["unknown"]),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(EditorError):
                validate_editor_settings(value)

    def test_external_backend_requires_normal_command(self):
        with self.assertRaisesRegex(EditorError, "requires external_command"):
            validate_editor_settings({
                "schema": 1, "backend": "external", "external_command": None,
                "external_wait_command": ["code", "--wait"], "language_packs": [],
            })

    def test_invalid_json_names_the_settings_file(self):
        path = editor_settings_path(self.home, "linux")
        path.parent.mkdir(parents=True)
        path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(EditorError, "editor.json"):
            resolve_editor_settings(self.home, "linux")

    def test_protected_windows_environment_path_uses_selected_home_fallback(self):
        fallback = editor_settings_path(self.home, "windows")
        fallback.parent.mkdir(parents=True)
        fallback.write_text(json.dumps({
            "schema": 1, "backend": "fresh", "external_command": None,
            "external_wait_command": None, "language_packs": ["go"],
        }), encoding="utf-8")
        protected = self.home.resolve() / "protected-service-profile"
        original = Path.read_text

        def read(path, *args, **kwargs):
            if protected in path.parents:
                raise PermissionError("service profile denied")
            return original(path, *args, **kwargs)

        with patch("dev_cockpit.editor.Path.read_text", autospec=True, side_effect=read):
            settings = resolve_editor_settings(
                self.home, "windows", {"APPDATA": str(protected)})
        self.assertEqual(settings.language_packs, ("go",))


class EditorPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="editor paths '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project @ unicode λ"
        self.project.mkdir()

    def test_literal_paths_are_absolute_and_preserved(self):
        names = ["space name.py", "quote's.py", "--leading", "colon:@.py", "line\nbreak.py"]
        for name in names:
            (self.project / name).write_text("fixture", encoding="utf-8")
        project, files = normalize_edit_paths(names, cwd=self.project)
        self.assertEqual(project, self.project)
        self.assertEqual(files, tuple(self.project / name for name in names))

    def test_single_directory_selects_project(self):
        child = self.project / "child"
        child.mkdir()
        self.assertEqual(normalize_edit_paths([child], cwd=self.project), (child, ()))

    def test_directory_and_file_mixture_is_rejected(self):
        file = self.project / "one.py"
        file.write_text("")
        with self.assertRaisesRegex(EditorError, "do not mix"):
            normalize_edit_paths([self.project, file], cwd=self.project)

    def test_new_file_requires_existing_writable_parent(self):
        project, files = normalize_edit_paths(["new.py"], cwd=self.project)
        self.assertEqual((project, files), (self.project, (self.project / "new.py",)))
        with self.assertRaisesRegex(EditorError, "parent"):
            normalize_edit_paths(["missing/new.py"], cwd=self.project)

    def test_permission_error_is_reported_as_inaccessible(self):
        target = self.project / "blocked.py"
        with patch("dev_cockpit.editor.Path.exists", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(EditorError, "not accessible"):
                normalize_edit_paths([target], cwd=self.project)

    def test_location_requires_one_file_and_positive_integers(self):
        path = self.project / "a.py"
        self.assertEqual(validate_location([path], 4, 2), (4, 2))
        for files, line, column in [([], 1, None), ([path, path], 1, None), ([path], 0, None), ([path], 1, -2), ([path], True, None), ([path], None, 2)]:
            with self.subTest(files=files, line=line, column=column), self.assertRaises(EditorError):
                validate_location(files, line, column)

    def test_identity_includes_canonical_worktree_and_session(self):
        sibling = self.root / "another/project @ unicode λ"
        sibling.mkdir(parents=True)
        key = project_identity(self.project, "dev-cockpit")
        self.assertEqual(key, project_identity(self.project / ".", "dev-cockpit"))
        self.assertNotEqual(key, project_identity(sibling, "dev-cockpit"))
        self.assertNotEqual(key, project_identity(self.project, "other"))


class EditorCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="editor command '")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.file = self.project / "a file & 'quote'.py"
        self.file.write_text("pass\n", encoding="utf-8")

    def test_fresh_command_is_an_argv_and_sets_managed_context(self):
        command = build_editor_command(
            EditorSettings(), [self.file], project=self.project,
            herdr_session="dev-cockpit", environment={"PATH": "/fixture"},
        )
        self.assertEqual(command.argv, ("fresh", str(self.file)))
        self.assertEqual(command.environment["PATH"], "/fixture")
        self.assertEqual(command.environment["DEV_COCKPIT_PROJECT"], str(self.project))
        self.assertEqual(command.environment["DEV_COCKPIT_HERDR_SESSION"], "dev-cockpit")
        self.assertEqual(command.environment["DEV_COCKPIT_EDITOR_KEY"],
                         project_identity(self.project, "dev-cockpit"))

    def test_external_normal_and_wait_commands_remain_argv(self):
        settings = EditorSettings(backend="external", external_command=("code", "--reuse-window"),
                                  external_wait_command=("code", "--reuse-window", "--wait"))
        normal = build_editor_command(settings, [self.file])
        waiting = build_editor_command(settings, [self.file], mode="wait")
        self.assertEqual(normal.argv, ("code", "--reuse-window", str(self.file)))
        self.assertEqual(waiting.argv, ("code", "--reuse-window", "--wait", str(self.file)))

    def test_external_wait_without_wait_argv_fails(self):
        settings = EditorSettings(backend="external", external_command=("code",))
        with self.assertRaisesRegex(EditorError, "external_wait_command"):
            build_editor_command(settings, [self.file], mode="wait")

    def test_persistent_route_and_ambiguous_location_fail_safely(self):
        with self.assertRaisesRegex(RoutingUnavailable, "Persistent"):
            build_editor_command(EditorSettings(), [self.file], mode="persistent")
        ambiguous = self.project / "colon:name.py"
        with self.assertRaisesRegex(RoutingUnavailable, "ambiguous"):
            build_editor_command(EditorSettings(), [ambiguous], location=(3, 2))

    def test_safe_fresh_foreground_location_uses_verified_positional_syntax(self):
        command = build_editor_command(EditorSettings(), [self.file], location=(3, 2))
        self.assertEqual(command.argv, ("fresh", str(self.file) + ":3:2"))

    def test_editor_pane_uses_named_session_and_shared_identity(self):
        command = build_editor_pane_command(
            EditorSettings(), self.project, "fixture", environment={"PATH": "/fixture"})
        key = project_identity(self.project, "fixture")
        self.assertEqual(command.argv, ("fresh", "-a", key))
        self.assertEqual(command.environment["DEV_COCKPIT_EDITOR_KEY"], key)

    def test_external_editor_cannot_be_embedded_in_terminal_pane(self):
        settings = EditorSettings(backend="external", external_command=("code",))
        with self.assertRaisesRegex(EditorError, "cannot be hosted"):
            build_editor_pane_command(settings, self.project, "fixture")

    def test_foreground_execution_uses_shell_false_and_returns_exit_code(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 7))
        request = EditorRequest(EditorSettings(), self.project, (self.file,), environment={"PATH": "/fixture"})
        self.assertEqual(open_files(request, runner=runner), 7)
        self.assertEqual(runner.call_args.args[0], ["fresh", str(self.file)])
        self.assertEqual(runner.call_args.kwargs["cwd"], str(self.project))
        self.assertFalse(runner.call_args.kwargs["shell"])

    def test_wait_selects_external_wait_command(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        settings = EditorSettings(backend="external", external_command=("code",),
                                  external_wait_command=("code", "--wait"))
        request = EditorRequest(settings, self.project, (self.file,), wait=True)
        self.assertEqual(open_files(request, runner=runner), 0)
        self.assertEqual(runner.call_args.args[0], ["code", "--wait", str(self.file)])

    def test_open_files_normalizes_relative_paths_against_project(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        request = EditorRequest(EditorSettings(), self.project, (Path(self.file.name),))
        open_files(request, runner=runner)
        self.assertEqual(runner.call_args.args[0], ["fresh", str(self.file)])


class EditorFallbackTests(unittest.TestCase):
    """Fresh must not be assumed usable before it is installed."""

    def test_qualified_platforms_are_reported(self):
        self.assertTrue(fresh_qualified("macos"))
        self.assertFalse(fresh_qualified("linux"))
        self.assertFalse(fresh_qualified("windows"))

    def test_external_backend_is_returned_unchanged(self):
        settings = EditorSettings(backend="external", external_command=("code",))
        self.assertEqual(effective_editor_settings(settings, target="linux"), settings)

    def test_installed_fresh_is_never_substituted(self):
        settings = EditorSettings()
        result = effective_editor_settings(settings, target="linux", finder=lambda name: "/tools/fresh")
        self.assertIs(result, settings)

    def test_missing_fresh_falls_back_to_existing_editor_without_splitting(self):
        # A bare path containing spaces must survive as one argv element, and a
        # multi-word value must not be word split into a broken executable.
        environment = {"EDITOR": "/Applications/My Editor/editor"}
        result = effective_editor_settings(EditorSettings(), target="linux",
                                           environment=environment, finder=lambda name: None)
        self.assertEqual(result.backend, "external")
        self.assertEqual(result.external_command, ("/Applications/My Editor/editor",))

    def test_missing_fresh_prefers_visual_over_editor(self):
        environment = {"VISUAL": "hx", "EDITOR": "nano"}
        result = effective_editor_settings(EditorSettings(), target="linux",
                                           environment=environment, finder=lambda name: None)
        self.assertEqual(result.external_command, ("hx",))

    def test_missing_fresh_and_missing_editor_is_an_actionable_error(self):
        with self.assertRaisesRegex(EditorError, "editor.json"):
            effective_editor_settings(EditorSettings(), target="linux", environment={}, finder=lambda name: None)

    def test_substitution_is_explained_with_the_platform_status(self):
        settings = EditorSettings()
        effective = effective_editor_settings(settings, target="linux",
                                              environment={"EDITOR": "nano"}, finder=lambda name: None)
        notice = describe_editor_substitution(settings, effective, "linux")
        self.assertIn("experimental", notice)
        self.assertIn("nano", notice)
        self.assertIsNone(describe_editor_substitution(settings, settings, "macos"))


class CodeLayoutSupportTests(unittest.TestCase):
    def test_unqualified_platform_keeps_the_classic_layout(self):
        supported, reason = code_layout_support("linux", finder=lambda name: "/tools/fresh")
        self.assertFalse(supported)
        self.assertIn("experimental", reason)
        self.assertIn("classic layout", reason)

    def test_qualified_platform_without_the_binary_explains_the_repair(self):
        supported, reason = code_layout_support("macos", finder=lambda name: None)
        self.assertFalse(supported)
        self.assertIn("not on PATH", reason)
        self.assertIn("Rerun setup", reason)

    def test_qualified_platform_with_fresh_is_usable(self):
        supported, reason = code_layout_support("macos", finder=lambda name: "/tools/fresh")
        self.assertTrue(supported)
        self.assertEqual(reason, "")

    def test_external_backend_is_reported_not_replaced_by_fresh(self):
        # A user who chose an external editor must not have it silently swapped
        # for a managed Fresh pane.
        settings = EditorSettings(backend="external", external_command=("code",))
        supported, reason = code_layout_support("macos", settings=settings,
                                                finder=lambda name: "/tools/fresh")
        self.assertFalse(supported)
        self.assertIn("external backend", reason)
        self.assertIn("classic layout", reason)


class EditorStatusTests(unittest.TestCase):
    def test_pack_aliases_and_all(self):
        self.assertEqual(canonical_language_packs(["javascript", "ts", "go"]), ("typescript", "go"))
        self.assertEqual(canonical_language_packs(["all"]),
                         ("go", "python", "java", "typescript", "cpp", "csharp", "rust", "bash"))

    def test_language_status_distinguishes_configured_and_missing(self):
        available = {"gopls": "/tools/gopls"}
        report = language_pack_status(EditorSettings(language_packs=("go",)), available.get)
        go = next(item for item in report if item["id"] == "go")
        python = next(item for item in report if item["id"] == "python")
        self.assertTrue(go["configured"])
        self.assertEqual(go["status"], "ready")
        self.assertFalse(python["configured"])
        self.assertEqual(python["status"], "missing")

    def test_permission_error_during_tool_discovery_means_missing(self):
        def denied(_name):
            raise PermissionError("protected service profile")
        self.assertTrue(all(item["status"] == "missing"
                            for item in language_pack_status(EditorSettings(), denied)))

    def test_doctor_reports_binary_version_project_and_foreground_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "fresh")
            Path(binary).write_text("fixture")
            Path(binary).chmod(0o755)
            run = Mock(return_value=subprocess.CompletedProcess([], 0, "fresh 0.5.1\n", ""))
            result = doctor_editor(
                EditorSettings(), home=directory, target="linux", project=directory,
                herdr_session="s", finder=lambda name: binary if name == "fresh" else None,
                runner=run,
            )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["version"], "fresh 0.5.1")
        self.assertEqual(result["routing"], "foreground")
        self.assertIn("editor_key", result)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_doctor_missing_binary_is_structured(self):
        result = doctor_editor(EditorSettings(), finder=lambda _name: None)
        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["version"])


if __name__ == "__main__":
    unittest.main()
