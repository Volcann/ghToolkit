import tempfile
import unittest
from pathlib import Path

from ghtoolkit import CommentCache, fetch_pr_user_comments


class MockAPI:
    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = responses

    def list(self, endpoint: str) -> list[dict]:
        return self.responses.get(endpoint, [])


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = Path(self.temp_dir.name) / "pr_comments.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cache_load_and_save(self):
        cache = CommentCache(self.cache_file)
        self.assertEqual(cache.load(), {})

        entries = [{"id": 1, "author": "volcann", "created_at": "2026-10-09T10:00:00Z", "body": "Fixed typo"}]
        cache.set_comments("org/repo", 10, entries)

        loaded = cache.get_comments("org/repo", 10)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["body"], "Fixed typo")

    def test_fetch_pr_user_comments_with_cache(self):
        mock = MockAPI({
            "issues/15/comments": [
                {"id": 101, "user": {"login": "volcann"}, "created_at": "2026-10-09T11:00:00Z", "body": "Issue comment"}
            ],
            "pulls/15/comments": [
                {"id": 102, "user": {"login": "volcann"}, "created_at": "2026-10-09T11:05:00Z", "body": "Inline review comment"}
            ],
            "pulls/15/reviews": [
                {"id": 103, "user": {"login": "other"}, "submitted_at": "2026-10-09T11:10:00Z", "body": "Other comment"},
                {"id": 104, "user": {"login": "volcann"}, "submitted_at": "2026-10-09T11:15:00Z", "body": "Review summary body"},
            ],
        })

        comments = fetch_pr_user_comments(
            mock,
            "org",
            "repo",
            15,
            author="volcann",
            target_date="2026-10-09",
            use_cache=True,
            cache_path=self.cache_file,
        )
        self.assertEqual(len(comments), 3)
        self.assertIn("Issue comment", comments)
        self.assertIn("Inline review comment", comments)
        self.assertIn("Review summary body", comments)

        # Subsequent call uses the cache
        mock.responses.clear()
        cached_comments = fetch_pr_user_comments(
            mock,
            "org",
            "repo",
            15,
            author="volcann",
            use_cache=True,
            cache_path=self.cache_file,
        )
        self.assertEqual(len(cached_comments), 3)


if __name__ == "__main__":
    unittest.main()
