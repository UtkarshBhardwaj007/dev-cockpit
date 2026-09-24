"""Content-addressed runtime deployment coverage (dev_cockpit.runtime)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dev_cockpit import runtime  # noqa: E402


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cockpit runtime ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"

    def test_runtime_files_requires_core_sources(self):
        files = runtime.runtime_files(ROOT)
        self.assertIn("bootstrap/cockpit.py", files)
        self.assertIn("dev_cockpit/cli.py", files)
        self.assertTrue(all(isinstance(v, str) and len(v) == 64 for v in files.values()))
        # Manifest/config inputs must be part of the runtime so the deployed
        # copy is self-contained.
        self.assertIn("manifests/tools.json", files)
        self.assertIn("manifests/downloads.json", files)
        self.assertIn("config/bridge/dev-edit", files)
        self.assertIn("config/fresh/config.json", files)

    def test_runtime_directory_is_predictable(self):
        self.assertEqual(
            runtime.runtime_directory(self.home),
            self.home.resolve() / ".local/share/dev-cockpit/runtime")

    def test_deploy_is_idempotent_and_content_addressed(self):
        first = runtime.deploy_runtime(ROOT, self.home)
        self.assertTrue(first.is_dir())
        self.assertTrue((first / "bootstrap/cockpit.py").is_file())
        self.assertTrue((first / "dev_cockpit/cli.py").is_file())
        # A second deploy with unchanged sources reuses the same version.
        second = runtime.deploy_runtime(ROOT, self.home)
        self.assertEqual(first, second)

    def test_modified_runtime_is_preserved_and_rejected(self):
        deployed = runtime.deploy_runtime(ROOT, self.home)
        target = deployed / "dev_cockpit/cli.py"
        original = target.read_bytes()
        target.write_bytes(original + b"\n# tampered\n")
        with self.assertRaises(ValueError):
            runtime.deploy_runtime(ROOT, self.home)
        # The tampered copy is preserved for inspection, not silently replaced.
        self.assertEqual(target.read_bytes(), original + b"\n# tampered\n")


if __name__ == "__main__":
    unittest.main()
