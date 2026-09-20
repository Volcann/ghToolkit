import os
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ghtoolkit import DiffStorageError
from ghtoolkit.diff_store import DiffStore
from tests.helpers import PATCH


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DiffStore(Path(self.directory.name) / "temp")

    def test_construction_does_not_create_temp_files(self):
        self.assertFalse(self.store.root.exists())

    def test_raw_bytes_and_whitespace_are_preserved(self):
        raw = PATCH + b"\t trailing spaces  \r\n\r\n"
        artifact = self.store.save("github.com/acme/widget", "pr", "7", raw)
        self.assertEqual(artifact.diff_path.read_bytes(), raw)
        self.assertTrue(artifact.markdown.startswith("```diff\n"))
        self.assertIn(raw.decode(), artifact.markdown)
        self.assertEqual(
            artifact.markdown_path.read_bytes(), artifact.markdown.encode()
        )
        self.assertTrue(artifact.diff_path.is_relative_to(self.store.root))

    def test_invalid_utf8_still_has_lossless_raw_file(self):
        artifact = self.store.save("a/b", "commit", "main", b"+\xff\n")
        self.assertEqual(artifact.diff_path.read_bytes(), b"+\xff\n")
        self.assertEqual(artifact.text, "+\ufffd\n")

    def test_markdown_fence_cannot_be_closed_by_patch_content(self):
        raw = b"+```python\n+example()\n+````\n"
        artifact = self.store.save("a/b", "pr", "7", raw)
        self.assertTrue(artifact.markdown.startswith("`````diff\n"))
        self.assertTrue(artifact.markdown.endswith("`````\n"))
        self.assertIn(raw.decode(), artifact.markdown)

    def test_no_final_newline_is_preserved_in_raw_file(self):
        artifact = self.store.save("a/b", "commit", "main", b"no final newline")
        self.assertEqual(artifact.diff_path.read_bytes(), b"no final newline")
        self.assertTrue(artifact.markdown.endswith("newline\n```\n"))

    def test_empty_diff_is_valid(self):
        artifact = self.store.save("a/b", "pr", "7", b"")
        self.assertEqual(artifact.diff_path.read_bytes(), b"")
        self.assertEqual(artifact.text, "")

    def test_repeat_calls_do_not_overwrite_previous_artifacts(self):
        first = self.store.save("a/b", "pr", "7", b"first")
        second = self.store.save("a/b", "pr", "7", b"second")
        self.assertNotEqual(first.diff_path, second.diff_path)
        self.assertEqual(first.diff_path.read_bytes(), b"first")

    def test_path_like_identifiers_cannot_escape_temp(self):
        artifact = self.store.save("../a/b", "commit", "../../escape", PATCH)
        self.assertTrue(artifact.diff_path.resolve().is_relative_to(self.store.root))

    def test_concurrent_saves_have_unique_paths(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(lambda _: self.store.save("a/b", "pr", "7", PATCH), range(12))
            )
        self.assertEqual(len({item.diff_path for item in results}), 12)
        self.assertTrue(all(item.diff_path.read_bytes() == PATCH for item in results))

    def test_storage_failure_is_reported_and_partial_files_removed(self):
        with patch.object(DiffStore, "_write", side_effect=OSError("disk full")):
            with self.assertRaises(DiffStorageError):
                self.store.save("a/b", "pr", "7", PATCH)
        self.assertEqual(list(self.store.root.rglob("changes.*")), [])

    @unittest.skipUnless(os.name == "posix", "POSIX permissions required")
    def test_diff_files_are_owner_only(self):
        artifact = self.store.save("a/b", "pr", "7", PATCH)
        self.assertEqual(artifact.diff_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(artifact.markdown_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(artifact.diff_path.parent.stat().st_mode & 0o777, 0o700)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_saved_unified_diff_passes_git_apply_check(self):
        artifact = self.store.save("a/b", "pr", "7", PATCH)
        workspace = Path(self.directory.name) / "workspace"
        workspace.mkdir()
        (workspace / "example.py").write_text("old()\n")
        result = subprocess.run(
            ["git", "apply", "--check", str(artifact.diff_path)],
            cwd=workspace,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_result_can_be_serialized_as_dictionary(self):
        artifact = self.store.save("a/b", "pr", "7", PATCH)
        self.assertIsInstance(artifact.as_dict()["diff_path"], str)
        self.assertEqual(artifact.as_dict()["text"], PATCH.decode())
