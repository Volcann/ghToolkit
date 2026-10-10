import tempfile
import unittest
from pathlib import Path

from ghtoolkit import ProgressQueue, get_pr_state, scan_foreign_pr

from tests.helpers import FakeRunner


class AuditTests(unittest.TestCase):
    def test_progress_queue_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "progress.txt"
            queue = ProgressQueue(path)
            self.assertTrue(queue.is_empty())

            queue.save(["org/repo:PR:1", "org/repo:Commit:abc1234"])
            self.assertEqual(queue.count(), 2)

            head = queue.pop()
            self.assertEqual(head, "org/repo:PR:1")
            self.assertEqual(queue.count(), 1)

            queue.push("org/repo:PR:2")
            self.assertEqual(queue.count(), 2)

            owner, repo, kind, ident = queue.parse_item("org/repo:PR:99")
            self.assertEqual(owner, "org")
            self.assertEqual(repo, "repo")
            self.assertEqual(kind, "PR")
            self.assertEqual(ident, "99")

    def test_scan_foreign_pr_matches_author_commits(self):
        runner = FakeRunner(
            json_results=[
                {
                    "labels": [{"name": "enhancement"}],
                    "commits": [
                        {
                            "oid": "1" * 40,
                            "messageHeadline": "Native contribution commit",
                            "authors": [{"login": "volcann", "name": "Mohsin Ali"}],
                        },
                        {
                            "oid": "2" * 40,
                            "messageHeadline": "Merge branch 'dev' into main",
                            "authors": [{"login": "volcann", "name": "Mohsin Ali"}],
                        },
                    ],
                }
            ]
        )

        num, is_match, messages = scan_foreign_pr(
            runner, "org/repo", 50, target_author="volcann"
        )
        self.assertEqual(num, 50)
        self.assertTrue(is_match)
        self.assertEqual(messages, ["Native contribution commit"])

    def test_scan_foreign_pr_ignores_invalid_labels(self):
        runner = FakeRunner(
            json_results=[
                {
                    "labels": [{"name": "spam"}],
                    "commits": [
                        {
                            "oid": "1" * 40,
                            "messageHeadline": "Some commit",
                            "authors": [{"login": "volcann"}],
                        }
                    ],
                }
            ]
        )

        num, is_match, messages = scan_foreign_pr(
            runner, "org/repo", 51, target_author="volcann"
        )
        self.assertEqual(num, 51)
        self.assertFalse(is_match)
        self.assertEqual(messages, [])

    def test_get_pr_state(self):
        runner = FakeRunner(json_results=[{"state": "MERGED"}])
        state = get_pr_state(runner, "org/repo", 100)
        self.assertEqual(state, "MERGED")


if __name__ == "__main__":
    unittest.main()
