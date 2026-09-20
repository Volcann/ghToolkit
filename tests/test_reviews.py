import json
import unittest
from pathlib import Path

from ghtoolkit import GitHubClient, GhCommandError
from tests.helpers import FakeRunner, SHA, rest_pr, review


class ReviewTests(unittest.TestCase):
    def client(self, runner, timezone="UTC"):
        return GitHubClient("acme/widget", runner=runner, timezone=timezone)

    def test_review_date_uses_submission_not_current_pr_updated_date(self):
        candidate = rest_pr(timestamp="2026-10-01T12:00:00Z")
        candidate["updated_at"] = "2026-10-06T12:00:00Z"
        runner = FakeRunner(
            json_results=[
                [[candidate]],
                [[review(), review(2, timestamp="2026-10-04T00:00:00Z")]],
            ]
        )
        result = self.client(runner).get_user_reviews_for_date("alice", "2026-10-03")
        self.assertEqual([item["id"] for item in result], [1])
        self.assertEqual(result[0]["pr_number"], 7)
        self.assertNotIn("updated:2026-10-03", str(runner.calls))

    def test_review_scan_skips_prs_created_after_the_day(self):
        runner = FakeRunner(
            json_results=[[[rest_pr(timestamp="2026-10-04T00:00:00Z")]]]
        )
        self.assertEqual(
            self.client(runner).get_user_reviews_for_date("alice", "2026-10-03"), []
        )
        self.assertEqual(len(runner.calls), 1)

    def test_review_scan_checks_author_and_excludes_pending(self):
        runner = FakeRunner(
            json_results=[
                [[review(1, "ALICE"), review(2, "bob"), review(3, timestamp=None)]]
            ]
        )
        result = self.client(runner).get_user_reviews_for_date(
            "alice", "2026-10-03", pr_numbers=[7, 7]
        )
        self.assertEqual([item["id"] for item in result], [1])
        self.assertEqual(len(runner.calls), 1)

    def test_review_scan_uses_timezone_boundaries(self):
        runner = FakeRunner(
            json_results=[
                [
                    [
                        review(1, timestamp="2026-10-02T19:00:00Z"),
                        review(2, timestamp="2026-10-03T19:00:00Z"),
                    ]
                ]
            ]
        )
        result = self.client(runner, "Asia/Karachi").get_user_reviews_for_date(
            "alice", "2026-10-03", pr_numbers=[7]
        )
        self.assertEqual([item["id"] for item in result], [1])

    def test_reviews_with_no_body_remain_in_review_results(self):
        runner = FakeRunner(json_results=[[[review(body="")]]])
        self.assertEqual(len(self.client(runner).get_pr_reviews(7)), 1)

    def test_comment_kinds_are_aggregated_without_id_collision(self):
        issue = {
            "id": 1,
            "body": "Issue",
            "user": {"login": "alice"},
            "created_at": "2026-10-03T12:00:00Z",
        }
        inline = {
            "id": 1,
            "body": "Inline",
            "user": {"login": "alice"},
            "created_at": "2026-10-03T13:00:00Z",
            "line": 42,
        }
        runner = FakeRunner(json_results=[[[review()]], [[issue]], [[inline]]])
        result = self.client(runner).fetch_pr_comments(7)
        self.assertEqual(len(result), 3)
        self.assertEqual(
            {item["kind"] for item in result}, {"issue", "inline", "review"}
        )
        self.assertEqual(
            next(item for item in result if item["kind"] == "inline")["line"], 42
        )

    def test_comment_date_and_author_filter(self):
        issue = {
            "id": 2,
            "body": "old",
            "user": {"login": "alice"},
            "created_at": "2026-10-02T12:00:00Z",
        }
        inline = {
            "id": 3,
            "body": "someone else",
            "user": {"login": "bob"},
            "created_at": "2026-10-03T12:00:00Z",
        }
        runner = FakeRunner(json_results=[[[review()]], [[issue]], [[inline]]])
        result = self.client(runner).fetch_pr_comments(
            7, date="2026-10-03", author="ALICE"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "review")

    def test_empty_review_bodies_are_not_comments(self):
        runner = FakeRunner(json_results=[[[review(body="")]], [[]], [[]]])
        self.assertEqual(self.client(runner).fetch_pr_comments(7), [])

    def test_inline_review_payload_preserves_suggestion_format(self):
        body = "Use this:\n\n```suggestion\nnew_call()\n```"
        comment = {"path": "src/example.py", "line": 42, "side": "RIGHT", "body": body}
        runner = FakeRunner(json_results=[{"id": 4, "state": "COMMENTED"}])
        result = self.client(runner).create_pull_request_review(
            7, SHA, [comment], body="Summary"
        )
        self.assertEqual(result["id"], 4)
        payload = json.loads(runner.calls[0][2]["input_text"])
        self.assertEqual(
            payload,
            {
                "commit_id": SHA,
                "event": "COMMENT",
                "comments": [comment],
                "body": "Summary",
            },
        )
        self.assertEqual(len(runner.calls), 1)

    def test_review_creation_is_never_retried(self):
        runner = FakeRunner(json_results=[GhCommandError(1, "connection dropped")])
        with self.assertRaises(GhCommandError):
            self.client(runner).create_pull_request_review(7, SHA, [], body="Summary")
        self.assertEqual(len(runner.calls), 1)

    def test_full_commit_sha_is_required(self):
        for sha in ("abc123", "z" * 40, None):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                self.client(FakeRunner()).create_pull_request_review(
                    7, sha, [], body="Summary"
                )

    def test_empty_review_is_rejected(self):
        with self.assertRaises(ValueError):
            self.client(FakeRunner()).create_pull_request_review(7, SHA, [])

    def test_invalid_inline_comments_are_rejected_before_posting(self):
        valid = {"path": "src/a.py", "line": 42, "side": "RIGHT", "body": "Fix this"}
        invalid = [
            {},
            {**valid, "line": 0},
            {**valid, "line": True},
            {**valid, "side": "TOP"},
            {**valid, "body": " "},
            {**valid, "path": "../a.py"},
            {**valid, "path": "/a.py"},
            {**valid, "start_line": 2},
            {**valid, "start_side": "RIGHT"},
            {**valid, "start_line": 43, "start_side": "RIGHT"},
            {**valid, "unexpected": "field"},
        ]
        for item in invalid:
            runner = FakeRunner()
            with self.subTest(comment=item), self.assertRaises(ValueError):
                self.client(runner).create_pull_request_review(7, SHA, [item])
            self.assertEqual(runner.calls, [])

    def test_multiline_review_comment_is_preserved(self):
        comment = {
            "path": "src/a.py",
            "line": 42,
            "side": "RIGHT",
            "body": "Fix this",
            "start_line": 40,
            "start_side": "RIGHT",
        }
        runner = FakeRunner(json_results=[{"id": 1}])
        self.client(runner).create_pull_request_review(7, SHA, [comment])
        self.assertEqual(
            json.loads(runner.calls[0][2]["input_text"])["comments"], [comment]
        )

    def test_comment_body_is_written_to_a_file_then_removed(self):
        body = "## Summary\nUnicode café\n"
        observed = {}

        class BodyRunner(FakeRunner):
            def run(self, *args, **kwargs):
                path = Path(args[args.index("--body-file") + 1])
                observed["path"] = path
                observed["body"] = path.read_bytes()
                return "https://github.com/acme/widget/pull/7#issuecomment-1\n"

        result = self.client(BodyRunner()).post_pr_comment(7, body)
        self.assertEqual(observed["body"], body.encode())
        self.assertFalse(observed["path"].exists())
        self.assertTrue(result.endswith("issuecomment-1"))

    def test_comment_temporary_file_is_removed_after_error(self):
        observed = {}

        class BodyRunner(FakeRunner):
            def run(self, *args, **kwargs):
                observed["path"] = Path(args[args.index("--body-file") + 1])
                raise GhCommandError(1, "failed")

        with self.assertRaises(GhCommandError):
            self.client(BodyRunner()).post_pr_comment(7, "Summary")
        self.assertFalse(observed["path"].exists())
