from datetime import date
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghtoolkit import GitHubClient, ProgressQueue
from tests.helpers import FakeRunner, gql_page, metadata, pr, rest_pr


class EcosystemCompatibilityTests(unittest.TestCase):
    """Verifies that all three consumer projects (lazy-reviewer, workedTask, volcanai)

    can seamlessly reuse ghToolkit's GitHubClient.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. lazy-reviewer Integration Tests
    # =========================================================================
    def test_lazy_reviewer_reuse_workflow(self):
        """Simulate lazy-reviewer's reviewer.py and github_client.py operations:

        - fetch_pr_metadata(repo_path, pr_number)
        - fetch_pr_diff(repo_path, pr_number)
        - checkout_pr_branch(repo_path, pr_number, local_repo_path)
        - post_pr_comment(repo_path, pr_number, body)
        - create_pull_request_review(repo_path, pr_number, commit_sha, inline_comments)
        """
        fake_sha = "a" * 40
        fake_meta = metadata()
        fake_meta["number"] = 101
        runner = FakeRunner(
            json_results=[
                fake_meta,  # pr view
                [gql_page(head=fake_meta["headRefOid"])],  # commits graphql
                {"id": 999},  # review post
            ],
            byte_results=[
                b"diff --git a/app.py b/app.py\n+print('hello')\n",  # pr diff
            ],
            text_results=[
                "Branch checked out\n",  # pr checkout
                "https://github.com/org/repo/issues/comments/1\n",  # pr comment
            ],
        )

        client = GitHubClient(runner=runner, temp_dir=self.temp_dir.name)

        # 1. Fetch metadata
        meta = client.fetch_pr_metadata("org/repo", 101)
        self.assertEqual(meta["number"], 101)
        self.assertEqual(meta["headRefOid"], fake_sha)

        # 2. Fetch diff directly as string
        diff_text = client.fetch_pr_diff("org/repo", 101)
        self.assertIn("print('hello')", diff_text)

        # 3. Checkout branch locally
        checkout_out = client.checkout_pr_branch("org/repo", 101, local_repo_path=self.temp_dir.name)
        self.assertIn("Branch checked out", checkout_out)

        # 4. Post review markdown comment
        comment_file = Path(self.temp_dir.name) / "review.md"
        comment_file.write_text("## Executive Summary\n\nLooks good!")
        post_out = client.post_pr_comment("org/repo", 101, str(comment_file))
        self.assertIn("issues/comments/1", post_out)

        # 5. Create PR review with inline comments
        inline_comments = [
            {"path": "app.py", "line": 1, "side": "RIGHT", "body": "```suggestion\nprint('welcome')\n```"}
        ]
        review_result = client.create_pull_request_review(
            "org/repo", 101, fake_sha, inline_comments, body="Auto review", event="COMMENT"
        )
        self.assertEqual(review_result["id"], 999)

    # =========================================================================
    # 2. workedTask Integration Tests
    # =========================================================================
    def test_worked_task_reuse_workflow(self):
        """Simulate workedTask's collector.py and github_client.py operations:

        - is_author_match with team aliases
        - get_user_commits_for_date(owner, repo, author, date, local_path)
        - get_user_prs_for_date(owner, repo, author, date, local_path)
        - get_pr_details(owner, repo, pr_number, local_path, author)
        - get_user_reviewed_prs_for_date(owner, repo, author, date, local_path)
        - get_pr_user_comments(owner, repo, pr_number, author, date)
        - get_commit_pull_requests(owner, repo, sha)
        - get_commit_branch(owner, repo, sha)
        """
        client = GitHubClient(runner=FakeRunner(), temp_dir=self.temp_dir.name)

        # 1. Alias matching
        self.assertTrue(client.is_author_match("Volcann", login="volcann"))
        self.assertTrue(client.is_author_match("Volcann", name="Mohsin Ali"))
        self.assertTrue(client.is_author_match("Volcann", email="mohsinmuhammad823@gmail.com"))

        # 2. Mock Local Git acceleration
        with patch("ghtoolkit.github_client.get_local_commits_for_date") as mock_commits, \
             patch("ghtoolkit.github_client.get_local_prs_for_date") as mock_prs, \
             patch("ghtoolkit.github_client.get_local_pr_details") as mock_pr_details, \
             patch("ghtoolkit.github_client.get_local_reviewed_prs_for_date") as mock_reviews, \
             patch("ghtoolkit.github_client.get_local_commit_pull_requests") as mock_commit_prs, \
             patch("ghtoolkit.github_client.get_local_commit_branch") as mock_commit_branch, \
             patch("ghtoolkit.github_client.fetch_pr_user_comments") as mock_comments:

            from ghtoolkit import CommitItem, PullRequestItem, ReviewItem

            mock_commits.return_value = [
                CommitItem({"sha": "1234567890ab", "message": "feat: add analytics\n\nDetails", "branch": "feature/analytics"})
            ]
            mock_prs.return_value = [
                PullRequestItem({"number": 202, "title": "Add analytics", "author_login": "Volcann", "state": "MERGED"})
            ]
            mock_pr_details.return_value = PullRequestItem({
                "number": 202,
                "title": "Add analytics",
                "author_login": "Volcann",
                "state": "MERGED",
                "files_changed": ["src/analytics.py"],
            })
            mock_reviews.return_value = [
                ReviewItem({"pr_number": 199, "pr_title": "Update billing", "reviewer": "Volcann", "state": "APPROVED"})
            ]
            mock_commit_prs.return_value = [{"number": 202}]
            mock_commit_branch.return_value = "feature/analytics"
            mock_comments.return_value = ["Approved, LGTM!"]

            target_date = date(2026, 10, 9)

            # Test workedTask-style multi-arg calls
            commits = client.get_user_commits_for_date("org", "repo", "Volcann", target_date, local_path=self.temp_dir.name)
            self.assertEqual(len(commits), 1)
            self.assertEqual(commits[0].sha, "1234567890ab")
            self.assertEqual(commits[0].headline, "feat: add analytics")
            self.assertEqual(commits[0].branch, "feature/analytics")

            prs = client.get_user_prs_for_date("org", "repo", "Volcann", target_date, local_path=self.temp_dir.name)
            self.assertEqual(len(prs), 1)
            self.assertEqual(prs[0].number, 202)
            self.assertEqual(prs[0].title, "Add analytics")

            pr_details = client.get_pr_details("org", "repo", 202, local_path=self.temp_dir.name, author="Volcann")
            self.assertEqual(pr_details.number, 202)
            self.assertEqual(pr_details.files_changed, ["src/analytics.py"])

            reviews = client.get_user_reviewed_prs_for_date("org", "repo", "Volcann", target_date, local_path=self.temp_dir.name)
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].pr_number, 199)
            self.assertEqual(reviews[0].reviewer, "Volcann")

            comments = client.get_pr_user_comments("org", "repo", 202, "Volcann", target_date=target_date)
            self.assertEqual(comments, ["Approved, LGTM!"])

            commit_prs = client.get_commit_pull_requests("org", "repo", "1234567890ab", local_path=self.temp_dir.name)
            self.assertEqual(commit_prs[0]["number"], 202)

            branch = client.get_commit_branch("org", "repo", "1234567890ab", local_path=self.temp_dir.name)
            self.assertEqual(branch, "feature/analytics")

    # =========================================================================
    # 3. volcanai Integration Tests
    # =========================================================================
    def test_volcanai_reuse_workflow(self):
        """Simulate volcanai's cron_job audit and metadata logging operations:

        - scan_contributor_contributions(owner, repo, author, limit, include_foreign)
        - get_all_prs(owner, repo, state, limit)
        - get_pr_state(owner, repo, pr_number)
        - fetch_pr_diff(owner, repo, pr_number)
        - get_commit_details(owner, repo, sha)
        - fetch_commit_diff(owner, repo, sha)
        - ProgressQueue tracking
        """
        runner = FakeRunner(
            json_results=[
                # get_all_prs
                [
                    {"number": 1, "author": {"login": "volcann"}},
                    {"number": 2, "author": {"login": "other"}},
                ],
                # scan_foreign_pr for PR #2
                {
                    "labels": [],
                    "commits": [
                        {
                            "oid": "9" * 40,
                            "messageHeadline": "Native contribution by Volcann",
                            "authors": [{"login": "volcann", "name": "Mohsin Ali"}],
                        }
                    ],
                },
                # get_pr_state
                {"state": "MERGED"},
                # get_commit_details (api.pages)
                [{"sha": "c" * 40, "commit": {"message": "Audit commit", "author": {"date": "2026-10-09T00:00:00Z"}}, "files": []}],
            ],
            byte_results=[
                b"diff --git a/audit.py b/audit.py\n+logged\n",  # fetch_pr_diff
                b"diff --git a/commit.py b/commit.py\n+commit diff\n",  # fetch_commit_diff
            ],
        )

        client = GitHubClient(runner=runner, temp_dir=self.temp_dir.name)

        # 1. High throughput scan of owned + foreign PRs
        owned_prs, commits = client.scan_contributor_contributions("org", "repo", "volcann", limit=100)
        self.assertEqual(owned_prs, [1, 2])
        self.assertEqual(commits, ["Native contribution by Volcann"])

        # 2. Resumable progress queue
        progress_file = Path(self.temp_dir.name) / "progress.txt"
        queue = ProgressQueue(progress_file)
        queue_items = [queue.make_pr_item("org", "repo", p) for p in owned_prs]
        queue.save(queue_items)
        self.assertEqual(queue.count(), 2)

        next_job = queue.pop()
        self.assertEqual(next_job, "org/repo:PR:1")
        self.assertEqual(queue.count(), 1)

        # 3. Check PR state for cleanup
        state = client.get_pr_state("org", "repo", 1)
        self.assertEqual(state, "MERGED")

        # 4. Fetch PR diff
        pr_diff = client.fetch_pr_diff("org/repo", 1)
        self.assertIn("+logged", pr_diff)

        # 5. Fetch commit details and diff
        commit_details = client.get_commit_details("org", "repo", "c" * 40)
        self.assertEqual(commit_details["sha"], "c" * 40)
        commit_diff = client.fetch_commit_diff("org/repo", "c" * 40)
        self.assertIn("+commit diff", commit_diff)


if __name__ == "__main__":
    unittest.main()
