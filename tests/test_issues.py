import tempfile
import unittest

from ghtoolkit.api import GhAPI, Repository
from ghtoolkit.issues import IssueService

from tests.helpers import FakeRunner


class IssueServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = Repository.parse("acme/widget")

    def test_module_import(self):
        from ghtoolkit import IssueService as ExportedIssueService  # noqa: PLC0415

        self.assertIs(IssueService, ExportedIssueService)

    def test_issue_comments_endpoint(self):
        fake_comments = [
            {"id": 1, "body": "First comment", "user": {"login": "alice"}},
            {"id": 2, "body": "Second comment", "user": {"login": "bob"}},
        ]
        runner = FakeRunner(json_results=[[fake_comments]])
        api = GhAPI(self.repo, runner)
        service = IssueService(api)

        comments = service.comments(42)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["body"], "First comment")
        self.assertIn("issues/42/comments", runner.calls[0][1][1])

    def test_issue_comments_invalid_number_rejected(self):
        api = GhAPI(self.repo, FakeRunner())
        service = IssueService(api)

        with self.assertRaises(ValueError):
            service.comments(0)
        with self.assertRaises(ValueError):
            service.comments(-5)
        with self.assertRaises(ValueError):
            service.comments("not_a_number")  # type: ignore[arg-type]

    def test_post_pr_comment_success(self):
        runner = FakeRunner(
            text_results=["https://github.com/acme/widget/pull/10#issuecomment-123\n"]
        )
        api = GhAPI(self.repo, runner)
        service = IssueService(api)

        result = service.post_pr_comment(10, "Looks good to me!")
        self.assertEqual(
            result, "https://github.com/acme/widget/pull/10#issuecomment-123"
        )
        self.assertEqual(len(runner.calls), 1)
        kind, args, kwargs = runner.calls[0]  # noqa: RUF059
        self.assertEqual(kind, "text")
        self.assertEqual(args[0:3], ("pr", "comment", "10"))
        self.assertIn("--body-file", args)

    def test_post_pr_comment_empty_body_rejected(self):
        api = GhAPI(self.repo, FakeRunner())
        service = IssueService(api)

        with self.assertRaises(ValueError):
            service.post_pr_comment(10, "")
        with self.assertRaises(ValueError):
            service.post_pr_comment(10, "   \n\t  ")


if __name__ == "__main__":
    unittest.main()
