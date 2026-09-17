"""Opt-in real Graphify CLI + stdio MCP tests against synthetic, local-only code.

GRAPHIFY_TEST_BIN must point at a directory containing graphify and graphify-mcp.
Install graphifyy[mcp]==0.9.57 separately in CI; these tests never install packages.
"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dev_cockpit import intelligence as subject


@unittest.skipUnless(os.environ.get("GRAPHIFY_TEST_BIN"), "Set GRAPHIFY_TEST_BIN for real Graphify integration")
class LiveGraphifyTests(unittest.TestCase):
    def test_index_query_repeat_edit_delete_and_disable(self):
        suffix = ".exe" if os.name == "nt" else ""
        tool_dir = Path(os.environ["GRAPHIFY_TEST_BIN"]).resolve()
        tools = tuple(str(tool_dir / (name + suffix)) for name in ("graphify", "graphify-mcp"))
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve() / "fixture with spaces"
            project.mkdir()
            (project / "maths.py").write_text("def add(a, b):\n    return a + b\n\ndef twice(n):\n    return add(n, n)\n")
            (project / "app.py").write_text("from maths import twice\n\ndef main():\n    return twice(4)\n")
            # A semantic document must never trigger model extraction in code-only mode.
            (project / "README.md").write_text("Synthetic design note; no model should receive this.\n")
            with patch.object(subject, "_graph_tools", return_value=tools), redirect_stdout(io.StringIO()):
                subject.graph_init(project)
                graph_path = project / subject.GRAPH
                graph = json.loads(graph_path.read_text())
                self.assertGreaterEqual(len(graph["nodes"]), 5)
                self.assertTrue(any("twice" in str(node) for node in graph["nodes"]))
                self.assertFalse(any("README.md" in str(node) for node in graph["nodes"]))
                self.assertEqual(subject.doctor(project, live=True), 0)
                probe = subject.mcp_probe(tools[1], graph_path, question="twice")
                self.assertIn("twice", json.dumps(probe["query"]))
                self.assertIn("query_graph", probe["tools"])
                before = graph_path.stat().st_mtime_ns
                subject.graph_init(project)
                self.assertEqual(before, graph_path.stat().st_mtime_ns)
                (project / "new_module.py").write_text("def shiny_new_feature():\n    return 17\n")
                self.assertEqual(subject.doctor(project), 1)
                subject.graph_update(project)
                self.assertIn("shiny_new_feature", graph_path.read_text())
                (project / "new_module.py").unlink()
                subject.graph_update(project)
                self.assertNotIn("shiny_new_feature", graph_path.read_text())
                subject.graph_disable(project)
                self.assertTrue(graph_path.exists())
                config = json.loads((project / subject.MCP_FILE).read_text())
                self.assertNotIn(subject.SERVER_NAME, config["mcpServers"])


@unittest.skipUnless(os.environ.get("OMP_TEST_BIN"), "Set OMP_TEST_BIN for real OMP configuration verification")
class LiveOMPTests(unittest.TestCase):
    def test_memory_overlay_is_accepted_by_native_omp_without_provider_calls(self):
        executable = str(Path(os.environ["OMP_TEST_BIN"]).resolve())
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            project = base / "project"
            project.mkdir()
            # Each child process gets an isolated HOME for OMP's hardcoded native
            # addon extraction cache; the parent process environment is untouched.
            fake_home = base / "isolated-user"
            fake_home.mkdir()
            env = {name: value for name, value in os.environ.items()
                   if name in {"PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG"}}
            env.update({"HOME": str(fake_home), "USERPROFILE": str(fake_home),
                        "PI_CONFIG_DIR": str(fake_home / ".omp"),
                        "PI_CODING_AGENT_DIR": str(fake_home / ".omp/agent"),
                        "PI_CONFIG_FILES": str(subject.ROOT / "config/intelligence/memory.yml")})
            for key, expected in {"memory.backend": "local", "autolearn.enabled": True,
                                  "memories.maxRolloutsPerStartup": 8, "memories.stage1Concurrency": 2,
                                  "memories.summaryInjectionTokenLimit": 3000}.items():
                result = subprocess.run([executable, "config", "get", key, "--json"],
                                        cwd=project, env=env, check=True, capture_output=True,
                                        text=True, encoding="utf-8", timeout=60)
                parsed = json.loads(result.stdout)
                self.assertEqual(parsed["key"], key)
                self.assertEqual(parsed["value"], expected)


if __name__ == "__main__":
    unittest.main()
