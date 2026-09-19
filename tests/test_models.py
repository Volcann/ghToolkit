import unittest

from ghtoolkit import (
    CommitInfo,
    CommitItem,
    ProjectConfig,
    PullRequestInfo,
    PullRequestItem,
    ReviewItem,
)


class ModelTests(unittest.TestCase):
    def test_commit_item_dict_and_attributes(self):
        item = CommitItem(
            {"hash": "c" * 40, "message": "Headline\n\nBody line 1\nBody line 2"}
        )
        self.assertEqual(item["hash"], "c" * 40)
        self.assertEqual(item.sha, "c" * 40)
        self.assertEqual(item.headline, "Headline")
        self.assertEqual(item.body, "Body line 1\nBody line 2")
        self.assertEqual(set(item), {"hash", "message"})

        info = item.to_info()
        self.assertIsInstance(info, CommitInfo)
        self.assertEqual(info.short_sha, "c" * 7)

    def test_pull_request_item_dict_and_attributes(self):
        raw = {
            "number": 42,
            "title": "Add Feature X",
            "body": "Implements X",
            "author": {"login": "dev1"},
            "state": "open",
            "headRefName": "feature-x",
        }
        item = PullRequestItem(raw)
        self.assertEqual(item.number, 42)
        self.assertEqual(item.title, "Add Feature X")
        self.assertEqual(item.author_login, "dev1")
        self.assertEqual(item.state, "OPEN")
        self.assertEqual(item.head_ref, "feature-x")
        self.assertTrue(item.is_own)
        self.assertEqual(item["number"], 42)

        info = item.to_info()
        self.assertIsInstance(info, PullRequestInfo)
        self.assertEqual(info.number, 42)
        self.assertEqual(info.head_ref, "feature-x")

    def test_review_item_dict_and_attributes(self):
        raw = {
            "pr_number": 99,
            "pr_title": "PR 99",
            "reviewer": "alice",
            "state": "APPROVED",
            "submitted_at": "2026-10-09T10:00:00Z",
        }
        item = ReviewItem(raw)
        self.assertEqual(item.pr_number, 99)
        self.assertEqual(item.reviewer, "alice")
        self.assertEqual(item.state, "APPROVED")
        self.assertEqual(item["pr_number"], 99)

        item.comments = ["Looks good!", "Ship it."]
        self.assertEqual(len(item.comments), 2)

    def test_project_config(self):
        cfg = ProjectConfig.from_dict(
            {
                "name": "Service-A",
                "owner": "org",
                "repo": "service-a-backend",
                "author": "Volcann",
                "local_path": "/path/to/code",
            }
        )
        self.assertEqual(cfg.full_name, "org/service-a-backend")
        self.assertEqual(cfg.category, "Backend")
        self.assertEqual(cfg.local_path, "/path/to/code")

        d = cfg.to_dict()
        self.assertEqual(d["name"], "Service-A")
        self.assertEqual(d["owner"], "org")


if __name__ == "__main__":
    unittest.main()
