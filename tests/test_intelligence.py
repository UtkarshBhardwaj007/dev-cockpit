"""Local state safety tests; no network, packages, credentials or model calls."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dev_cockpit import intelligence as subject


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve() / "project with spaces"
        self.project.mkdir()
        self.quiet = io.StringIO()
        self.capture = redirect_stdout(self.quiet)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def test_memory_enable_repeat_disable_preserves_existing_omp(self):
        config = self.project / ".omp/config.yml"
        config.parent.mkdir()
        original = b"# User config, including a different backend\nmemory:\n  backend: mnemopi\ncustom: keep\n"
        config.write_bytes(original)
        subject.memory_enable(self.project)
        overlay = self.project / subject.MEMORY_OVERLAY
        before = overlay.stat().st_mtime_ns
        subject.memory_enable(self.project)
        self.assertEqual(before, overlay.stat().st_mtime_ns)
        command = subject.omp_command(self.project, "path with spaces/omp")
        self.assertEqual(command, ["path with spaces/omp", "--config", str(overlay)])
        self.assertIn("backend: local", overlay.read_text())
        subject.memory_disable(self.project)
        self.assertFalse(overlay.exists())
        self.assertEqual(subject.omp_command(self.project), ["omp"])
        self.assertEqual(config.read_bytes(), original)

    def test_memory_notes_persist_deduplicate_and_stay_project_scoped(self):
        subject.memory_remember(self.project, "Queue retries use exponential backoff.")
        subject.memory_remember(self.project, "Queue retries use exponential backoff.")
        subject.memory_enable(self.project)
        notes = subject.memory_show(self.project)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "Queue retries use exponential backoff.")
        other = self.project.parent / "other"
        other.mkdir()
        self.assertEqual(subject.memory_show(other), [])
        subject.memory_disable(self.project)
        self.assertEqual(subject.memory_show(self.project), notes)
        self.assertEqual((self.project / subject.LOCAL / ".gitignore").read_text(), "*\n")

    def test_edited_owned_files_are_preserved_and_disabled_overlay_is_unused(self):
        subject.memory_enable(self.project)
        overlay = self.project / subject.MEMORY_OVERLAY
        overlay.write_text("memory:\n  backend: off\n")
        with self.assertRaisesRegex(ValueError, "preserved"):
            subject.memory_enable(self.project)
        subject.memory_disable(self.project)
        self.assertEqual(overlay.read_text(), "memory:\n  backend: off\n")
        self.assertEqual(subject.omp_command(self.project), ["omp"])

    def test_existing_foreign_overlay_and_rule_are_never_owned(self):
        overlay = self.project / subject.MEMORY_OVERLAY
        overlay.parent.mkdir(parents=True)
        overlay.write_text("memory:\n  backend: local\n")
        with self.assertRaises(ValueError):
            subject.memory_enable(self.project)
        subject.memory_disable(self.project)
        self.assertTrue(overlay.exists())

    def test_mcp_merge_and_disable_preserve_unrelated_entries_and_fields(self):
        config = self.project / subject.MCP_FILE
        config.parent.mkdir()
        before = {"custom": ["preserve"], "disabledServers": ["foreign"],
                  "mcpServers": {"foreign": {"command": "user-tool"}}}
        config.write_text(json.dumps(before))
        state = {"files": {}}
        subject._register_mcp(self.project, state, "/path with spaces/graphify-mcp")
        created = json.loads(config.read_text())
        self.assertEqual(created["custom"], before["custom"])
        self.assertEqual(created["mcpServers"]["foreign"], before["mcpServers"]["foreign"])
        self.assertEqual(created["mcpServers"][subject.SERVER_NAME]["args"], [str(self.project / subject.GRAPH)])
        old_mtime = config.stat().st_mtime_ns
        subject._register_mcp(self.project, state, "/path with spaces/graphify-mcp")
        self.assertEqual(config.stat().st_mtime_ns, old_mtime)
        subject._register_mcp(self.project, state, None, remove=True)
        self.assertEqual(json.loads(config.read_text()), before)

    def test_user_edited_mcp_entry_survives_disable(self):
        state = {"files": {}}
        subject._register_mcp(self.project, state, "graphify-mcp")
        config = self.project / subject.MCP_FILE
        edited = json.loads(config.read_text())
        edited["mcpServers"][subject.SERVER_NAME]["args"] = ["my-graph.json"]
        config.write_text(json.dumps(edited))
        subject._register_mcp(self.project, state, None, remove=True)
        self.assertEqual(json.loads(config.read_text()), edited)

    def test_conflicting_mcp_prevents_index(self):
        config = self.project / subject.MCP_FILE
        config.parent.mkdir()
        config.write_text(json.dumps({"mcpServers": {subject.SERVER_NAME: {"command": "user-tool"}}}))
        with patch.object(subject, "_require_graphify", return_value=("graphify", "graphify-mcp")), \
                patch.object(subject, "graph_update") as index:
            with self.assertRaisesRegex(ValueError, "already exists"):
                subject.graph_init(self.project)
            index.assert_not_called()

    def test_source_fingerprint_tracks_content_and_deletions_not_managed_files(self):
        source = self.project / "app.py"
        source.write_text("x = 1\n")
        first = subject._source_fingerprint(self.project)
        subject.memory_enable(self.project)
        self.assertEqual(first, subject._source_fingerprint(self.project))
        source.write_text("x = 2\n")
        self.assertNotEqual(first, subject._source_fingerprint(self.project))
        source.unlink()
        self.assertNotEqual(first, subject._source_fingerprint(self.project))

    def test_index_failure_restores_previous_graph_and_does_not_advance_fingerprint(self):
        graph = self.project / subject.GRAPH
        graph.parent.mkdir(parents=True)
        original = b'{"nodes":[{"id":"a","label":"old"}],"edges":[]}'
        graph.write_bytes(original)
        subject._save(self.project, {"files": {}, "source_fingerprint": "old"})
        def bad_run(command, **kwargs):
            graph.write_text('{"oops":true}')
            raise subprocess.CalledProcessError(1, command)
        with patch.object(subject, "_require_graphify", return_value=("graphify", "graphify-mcp")), \
                patch.object(subject.subprocess, "run", side_effect=bad_run):
            with self.assertRaises(subprocess.CalledProcessError):
                subject.graph_update(self.project)
        self.assertEqual(graph.read_bytes(), original)
        self.assertEqual(subject._state(self.project)["source_fingerprint"], "old")

    def test_unchanged_index_does_not_run_extraction(self):
        graph = self.project / subject.GRAPH
        graph.parent.mkdir(parents=True)
        graph.write_text('{"nodes":[],"edges":[]}')
        subject._save(self.project, {"files": {}, "source_fingerprint": subject._source_fingerprint(self.project)})
        with patch.object(subject, "_require_graphify", return_value=("graphify", "graphify-mcp")), \
                patch.object(subject.subprocess, "run") as run:
            self.assertEqual(subject.graph_update(self.project), graph)
            run.assert_not_called()

    def test_existing_usable_graphify_is_not_reinstalled(self):
        with patch.object(subject, "_graph_tools", return_value=("existing/graphify", "existing/graphify-mcp")), \
                patch.object(subject, "_check_tools", return_value=True), \
                patch.object(subject.subprocess, "run") as run:
            self.assertEqual(subject.install_graphify(self.project), ("existing/graphify", "existing/graphify-mcp"))
            run.assert_not_called()

    def test_cli_help_alone_does_not_mistake_missing_mcp_extra_for_usable_install(self):
        with patch.object(subject.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "extract --code-only")), \
                patch.object(subject, "mcp_probe", side_effect=ValueError("No module named mcp")) as probe:
            self.assertFalse(subject._check_tools(("graphify", "graphify-mcp")))
            probe.assert_called_once()

    def test_new_install_is_private_pinned_and_no_implicit_reinstall(self):
        with patch.object(subject, "_graph_tools", return_value=("g", "m")), \
                patch.object(subject, "_check_tools", side_effect=[False, True]), \
                patch.object(subject.shutil, "which", return_value="uv"), \
                patch.object(subject.subprocess, "run") as run:
            subject.install_graphify(self.project)
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["uv", "tool", "install", "--python", "3.12", subject.GRAPHIFY_PACKAGE])
            self.assertEqual(kwargs["env"]["UV_TOOL_BIN_DIR"], str(subject.graph_bin(self.project)))

    def test_symlink_and_invalid_json_are_rejected_without_overwrite(self):
        outside = self.project.parent / "outside"
        outside.mkdir()
        try:
            (self.project / ".omp").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation requires platform privileges")
        with self.assertRaisesRegex(ValueError, "symlink"):
            subject.memory_enable(self.project)
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_mcp_is_not_replaced(self):
        path = self.project / subject.MCP_FILE
        path.parent.mkdir()
        path.write_text('{"mcpServers":[]}')
        with self.assertRaises(ValueError):
            subject._register_mcp(self.project, {"files": {}}, "g")
        self.assertEqual(path.read_text(), '{"mcpServers":[]}')

    def test_lock_prevents_simultaneous_mutations(self):
        with subject._locked(self.project):
            with self.assertRaisesRegex(ValueError, "already running"):
                subject.memory_enable(self.project)
        subject.memory_enable(self.project)

    def test_cli_missing_dependency_is_actionable_nonzero(self):
        with patch.object(subject, "_check_tools", return_value=False), redirect_stderr(self.quiet):
            self.assertEqual(subject.main(["graph", "init", str(self.project)]), 1)
        self.assertIn("dev graph install", self.quiet.getvalue())


if __name__ == "__main__":
    unittest.main()
