import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock
import uuid

from dev_cockpit.workspace import (Herdr, HerdrError, _read_response,
                                   editor_key, ensure_project_tab,
                                   ensure_code_editor, ensure_workspace, layout_tree,
                                   pane_environment, workspace_label)


class WorkspaceTests(unittest.TestCase):
    def test_read_response_handles_chunks_and_notifications(self):
        stream = iter([b'{"event":"update"}\n{"id":"r",', b'"result":{"ok":true}}\n'])
        self.assertEqual(_read_response(lambda: next(stream), "r")["result"], {"ok": True})

    def test_truncated_response_fails(self):
        with self.assertRaises(HerdrError):
            _read_response(lambda: b"", "r")

    def test_layout_uses_argv_for_paths_with_shell_metacharacters(self):
        layout = layout_tree("project with 'quotes' & space", ["omp", "--config", "file & ' quote"], ["yazi"])
        self.assertEqual(layout["first"]["first"]["command"], ["omp", "--config", "file & ' quote"])
        self.assertEqual(layout["second"]["label"], "Shell")

    def test_code_layout_has_editor_agent_shell_and_explicit_context(self):
        with tempfile.TemporaryDirectory() as d:
            layout = layout_tree(d, ["omp"], editor_command=["fresh", "-a", "fixture"],
                                 session="fixture", layout="code")
            self.assertEqual(layout["ratio"], 0.78)
            self.assertEqual(layout["first"]["ratio"], 0.68)
            self.assertEqual(layout["first"]["first"]["label"], "Editor")
            self.assertEqual(layout["first"]["second"]["label"], "OMP")
            self.assertEqual(layout["second"]["label"], "Shell")
            expected = pane_environment(d, "fixture")
            self.assertEqual(layout["first"]["first"]["env"], expected)
            self.assertEqual(expected["DEV_COCKPIT_EDITOR_KEY"], editor_key(d, "fixture"))

    def test_code_layout_requires_editor_command(self):
        with self.assertRaisesRegex(ValueError, "editor command"):
            layout_tree(".", ["omp"], layout="code")

    def test_reuses_existing_without_restarting_anything(self):
        with tempfile.TemporaryDirectory() as d:
            client = Mock()
            client.cli.side_effect = [{"workspaces": [{"workspace_id": "w9", "label": workspace_label(d)}]}, {}]
            result = ensure_workspace(client, d)
            self.assertFalse(result["created"])
            client.request.assert_not_called()
            self.assertEqual(client.cli.call_args_list[-1].args, ("workspace", "focus", "w9"))

    def test_layout_failure_does_not_kill_potentially_started_processes(self):
        with tempfile.TemporaryDirectory() as d:
            client = Mock()
            client.cli.side_effect = [{"workspaces": []}, {"workspace": {"workspace_id": "w1"}, "tab": {"tab_id": "w1:t1"}}]
            client.request.side_effect = TimeoutError("uncertain reply")
            with self.assertRaisesRegex(HerdrError, "preserved"):
                ensure_workspace(client, d)
            self.assertEqual(client.cli.call_count, 2)

    def test_project_tab_is_created_once_then_focused(self):
        with tempfile.TemporaryDirectory() as d:
            workspace = {"workspace_id": "w1", "label": workspace_label(d)}
            client = Mock()
            client.cli.side_effect = [
                {"workspaces": [workspace]},
                {"snapshot": {"tabs": [], "panes": []}},
                {"tab": {"tab_id": "w1:t2"}, "root_pane": {"pane_id": "w1:p4"}},
            ]
            client.request.side_effect = [
                {"ok": True},
            ]
            result = ensure_project_tab(client, d, "Files", ["yazi", d])
            self.assertTrue(result["created"])
            self.assertEqual(client.cli.call_args_list[2].args[:2], ("tab", "create"))
            root = client.request.call_args_list[0].args[1]["root"]
            self.assertEqual(root["command"], ["yazi", d])

            client.reset_mock()
            client.cli.side_effect = [
                {"workspaces": [workspace]},
                {"snapshot": {
                    "tabs": [{"workspace_id": "w1", "tab_id": "w1:t2", "label": "Files"}],
                    "panes": [{"tab_id": "w1:t2", "pane_id": "w1:p4", "label": "Files"}],
                }},
            ]
            client.request.side_effect = [
                {"ok": True},
                {"ok": True},
            ]
            result = ensure_project_tab(client, d, "Files", ["yazi", d])
            self.assertFalse(result["created"])
            self.assertEqual([call.args[0] for call in client.request.call_args_list],
                             ["tab.focus", "pane.focus"])

    def test_project_tab_failure_preserves_created_tab(self):
        with tempfile.TemporaryDirectory() as d:
            client = Mock()
            workspace = {"workspace_id": "w1", "label": workspace_label(d)}
            client.cli.side_effect = [
                {"workspaces": [workspace]},
                {"snapshot": {"tabs": [], "panes": []}},
                {"tab": {"tab_id": "w1:t2"}},
            ]
            client.request.side_effect = TimeoutError("uncertain reply")
            with self.assertRaisesRegex(HerdrError, "preserved"):
                ensure_project_tab(client, d, "Review", ["lazygit"])

    def test_existing_code_editor_is_focused_without_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            client = Mock()
            client.cli.return_value = {"snapshot": {"panes": [{
                "workspace_id": "w1", "tab_id": "w1:t1", "pane_id": "w1:p1",
                "label": "Editor",
            }]}}
            result = ensure_code_editor(client, d, "w1", ["fresh", "-a", "key"])
            self.assertFalse(result["created"])
            self.assertEqual([call.args[0] for call in client.request.call_args_list],
                             ["tab.focus", "pane.focus"])

    def test_duplicate_code_editors_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            client = Mock()
            client.cli.return_value = {"snapshot": {"panes": [
                {"workspace_id": "w1", "label": "Editor"},
                {"workspace_id": "w1", "label": "Editor"},
            ]}}
            with self.assertRaisesRegex(HerdrError, "Multiple managed Editor"):
                ensure_code_editor(client, d, "w1", ["fresh", "-a", "key"])


@unittest.skipUnless(os.environ.get("COCKPIT_HERDR_TEST_BIN"), "Set COCKPIT_HERDR_TEST_BIN for a real Herdr server test")
class RealHerdrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dc-", dir="/private/tmp" if os.path.isdir("/private/tmp") else None)
        self.base = Path(self.temp.name).resolve()
        self.binary = os.environ["COCKPIT_HERDR_TEST_BIN"]
        config = self.base / "config.toml"
        shell = "powershell.exe" if os.name == "nt" else "/bin/sh"
        config.write_text('onboarding = false\n[terminal]\ndefault_shell = ' + json.dumps(shell) + '\nshell_mode = "non_login"\n[update]\nversion_check = false\nmanifest_check = false\n', encoding="utf-8")
        endpoint = r"\\.\pipe\herdr-cockpit-test-" + uuid.uuid4().hex if os.name == "nt" else str(self.base / "api.sock")
        self.env = dict(os.environ, HERDR_CONFIG_PATH=str(config), XDG_CONFIG_HOME=str(self.base),
                        HERDR_SOCKET_PATH=endpoint, HERDR_DISABLE_SOUND="1")
        # Override Herdr's APPDATA on Windows without changing the user's HOME.
        if os.name == "nt":
            self.env["APPDATA"] = str(self.base)
        self.client = Herdr(self.binary, "test", self.env)
        self.client.ensure_server()

    def tearDown(self):
        try:
            self.client.cli("server", "stop", json_output=False)
        except (HerdrError, subprocess.TimeoutExpired):
            pass
        if hasattr(self.client, "started_process"):
            self.client.started_process.wait(timeout=5)
        time.sleep(.15)
        self.temp.cleanup()

    def test_real_layout_is_reused_and_shell_is_controllable(self):
        first = ensure_workspace(self.client, self.base,
                                 ["python" if os.name == "nt" else "python3", "-u", "-c", "import time; print('AGENT_FIXTURE_READY',flush=True); time.sleep(60)"],
                                 ["python" if os.name == "nt" else "python3", "-u", "-c", "import time; print('FILES_FIXTURE_READY',flush=True); time.sleep(60)"])
        second = ensure_workspace(self.client, self.base)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["workspace_id"], second["workspace_id"])
        snapshot = self.client.cli("api", "snapshot")["snapshot"]
        panes = [p for p in snapshot["panes"] if p["workspace_id"] == first["workspace_id"]]
        self.assertEqual(len(panes), 3)
        shell = next(p for p in panes if p.get("label") == "Shell")
        self.client.cli("pane", "run", shell["pane_id"], "echo COCKPIT_SHELL_WORKS", json_output=False)
        self.client.cli("pane", "wait-output", shell["pane_id"], "--match", "COCKPIT_SHELL_WORKS", "--timeout", "5000")
        # Provisioning again leaves original terminal identities alive.
        after = self.client.cli("api", "snapshot")["snapshot"]
        self.assertEqual({p["terminal_id"] for p in panes}, {p["terminal_id"] for p in after["panes"]})


if __name__ == "__main__":
    unittest.main()
