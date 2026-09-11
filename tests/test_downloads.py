"""Coverage for download/extract safety branches not exercised via packages."""
import io
import os
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dev_cockpit.downloads import _safe_name, extract_archive  # noqa: E402


class SafeNameTests(unittest.TestCase):
    def test_accepts_safe_relative_paths(self):
        self.assertEqual(_safe_name("dir/file.txt"), PurePosixPath("dir/file.txt"))
        self.assertEqual(_safe_name("file.txt"), PurePosixPath("file.txt"))

    def test_rejects_absolute_traversal_and_drive(self):
        for bad in ("/etc/passwd", "a/../b", "../escape", "C:/Windows/x", "a\\..\\b"):
            with self.assertRaises(ValueError, msg=bad):
                _safe_name(bad)


class ExtractArchiveTests(unittest.TestCase):
    def _tar(self, members, mode=0o644):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for name, data in members:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = mode
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_tar_extracts_regular_file_with_mode(self):
        with tempfile.TemporaryDirectory(prefix="dc-tar ") as tmp:
            dest = Path(tmp) / "out"
            blob = self._tar([("bin/tool", b"#!/bin/sh\necho hi\n")], mode=0o755)
            archive = Path(tmp) / "a.tar"
            archive.write_bytes(blob)
            extract_archive(archive, dest)
            target = dest / "bin/tool"
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), b"#!/bin/sh\necho hi\n")
            if os.name != "nt":
                self.assertTrue(target.stat().st_mode & 0o100)  # owner-execute preserved

    def test_tar_rejects_symlink(self):
        with tempfile.TemporaryDirectory(prefix="dc-tarlink ") as tmp:
            dest = Path(tmp) / "out"
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            archive = Path(tmp) / "a.tar"
            archive.write_bytes(buf.getvalue())
            with self.assertRaises(ValueError):
                extract_archive(archive, dest)

    def test_zip_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory(prefix="dc-ziplink ") as tmp:
            dest = Path(tmp) / "out"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, "/etc/passwd")
            archive = Path(tmp) / "a.zip"
            archive.write_bytes(buf.getvalue())
            with self.assertRaises(ValueError):
                extract_archive(archive, dest)


if __name__ == "__main__":
    unittest.main()
