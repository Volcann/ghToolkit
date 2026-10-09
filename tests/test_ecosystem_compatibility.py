from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghtoolkit import GitHubClient, ProgressQueue
from tests.helpers import FakeRunner, gql_page, metadata


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
        checkout_out = client.checkout_pr_branch(
            "org/repo", 101, local_repo_path=self.temp_dir.name
        )
        self.assertIn("Branch checked out", checkout_out)

        # 4. Post review markdown comment
        comment_file = Path(self.temp_dir.name) / "review.md"
        comment_file.write_text("## Executive Summary\n\nLooks good!")
        post_out = client.post_pr_comment("org/repo", 101, str(comment_file))
        self.assertIn("issues/comments/1", post_out)

        # 5. Create PR review with inline comments
        inline_comments = [
            {
                "path": "app.py",
                "line": 1,
                "side": "RIGHT",
                "body": "```suggestion\nprint('welcome')\n```",
            }
        ]
        review_result = client.create_pull_request_review(
            "org/repo",
            101,
            fake_sha,
            inline_comments,
            body="Auto review",
            event="COMMENT",
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
        self.assertTrue(
            client.is_author_match("Volcann", email="mohsinmuhammad823@gmail.com")
        )

        # 2. Mock Local Git acceleration
        with (
            patch("ghtoolkit.github_client.get_local_commits_for_date") as mock_commits,
            patch("ghtoolkit.github_client.get_local_prs_for_date") as mock_prs,
            patch("ghtoolkit.github_client.get_local_pr_details") as mock_pr_details,
            patch(
                "ghtoolkit.github_client.get_local_reviewed_prs_for_date"
            ) as mock_reviews,
            patch(
                "ghtoolkit.github_client.get_local_commit_pull_requests"
            ) as mock_commit_prs,
            patch(
                "ghtoolkit.github_client.get_local_commit_branch"
            ) as mock_commit_branch,
            patch("ghtoolkit.github_client.fetch_pr_user_comments") as mock_comments,
        ):
            from ghtoolkit import CommitItem, PullRequestItem, ReviewItem

            mock_commits.return_value = [
                CommitItem(
                    {
                        "sha": "1234567890ab",
                        "message": "feat: add analytics\n\nDetails",
                        "branch": "feature/analytics",
                    }
                )
            ]
            mock_prs.return_value = [
                PullRequestItem(
                    {
                        "number": 202,
                        "title": "Add analytics",
                        "author_login": "Volcann",
                        "state": "MERGED",
                    }
                )
            ]
            mock_pr_details.return_value = PullRequestItem(
                {
                    "number": 202,
                    "title": "Add analytics",
                    "author_login": "Volcann",
                    "state": "MERGED",
                    "files_changed": ["src/analytics.py"],
                }
            )
            mock_reviews.return_value = [
                ReviewItem(
                    {
                        "pr_number": 199,
                        "pr_title": "Update billing",
                        "reviewer": "Volcann",
                        "state": "APPROVED",
                    }
                )
            ]
            mock_commit_prs.return_value = [{"number": 202}]
            mock_commit_branch.return_value = "feature/analytics"
            mock_comments.return_value = ["Approved, LGTM!"]

            target_date = date(2026, 10, 9)

            # Test workedTask-style multi-arg calls
            commits = client.get_user_commits_for_date(
                "org", "repo", "Volcann", target_date, local_path=self.temp_dir.name
            )
            self.assertEqual(len(commits), 1)
            self.assertEqual(commits[0].sha, "1234567890ab")
            self.assertEqual(commits[0].headline, "feat: add analytics")
            self.assertEqual(commits[0].branch, "feature/analytics")

            prs = client.get_user_prs_for_date(
                "org", "repo", "Volcann", target_date, local_path=self.temp_dir.name
            )
            self.assertEqual(len(prs), 1)
            self.assertEqual(prs[0].number, 202)
            self.assertEqual(prs[0].title, "Add analytics")

            pr_details = client.get_pr_details(
                "org", "repo", 202, local_path=self.temp_dir.name, author="Volcann"
            )
            self.assertEqual(pr_details.number, 202)
            self.assertEqual(pr_details.files_changed, ["src/analytics.py"])

            reviews = client.get_user_reviewed_prs_for_date(
                "org", "repo", "Volcann", target_date, local_path=self.temp_dir.name
            )
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].pr_number, 199)
            self.assertEqual(reviews[0].reviewer, "Volcann")

            comments = client.get_pr_user_comments(
                "org", "repo", 202, "Volcann", target_date=target_date
            )
            self.assertEqual(comments, ["Approved, LGTM!"])

            commit_prs = client.get_commit_pull_requests(
                "org", "repo", "1234567890ab", local_path=self.temp_dir.name
            )
            self.assertEqual(commit_prs[0]["number"], 202)

            branch = client.get_commit_branch(
                "org", "repo", "1234567890ab", local_path=self.temp_dir.name
            )
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
                [
                    {
                        "sha": "c" * 40,
                        "commit": {
                            "message": "Audit commit",
                            "author": {"date": "2026-10-09T00:00:00Z"},
                        },
                        "files": [],
                    }
                ],
            ],
            byte_results=[
                b"diff --git a/audit.py b/audit.py\n+logged\n",  # fetch_pr_diff
                b"diff --git a/commit.py b/commit.py\n+commit diff\n",  # fetch_commit_diff
            ],
        )

        client = GitHubClient(runner=runner, temp_dir=self.temp_dir.name)

        # 1. High throughput scan of owned + foreign PRs
        owned_prs, commits = client.scan_contributor_contributions(
            "org", "repo", "volcann", limit=100
        )
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

    # =========================================================================
    # 4. HR-Tool Project Config & Multi-Repo Verification
    # =========================================================================
    def test_project_json_configuration_loading(self):
        """Verify project.json holds exact HR-Tool projects and loads cleanly."""
        projects = GitHubClient.load_projects("project.json")
        self.assertEqual(len(projects), 2)

        backend = projects[0]
        self.assertEqual(backend.name, "HR-Tool")
        self.assertEqual(backend.category, "Backend")
        self.assertEqual(backend.owner, "folium-hr-management-tool")
        self.assertEqual(backend.repo, "hr-tool-backend")
        self.assertEqual(
            backend.local_path, "/home/folium/Documents/HR-Tool/hr-tool-backend"
        )
        self.assertEqual(backend.author, "Volcann")
        self.assertEqual(backend.full_name, "folium-hr-management-tool/hr-tool-backend")

        frontend = projects[1]
        self.assertEqual(frontend.name, "HR-Tool")
        self.assertEqual(frontend.category, "Frontend")
        self.assertEqual(frontend.owner, "folium-hr-management-tool")
        self.assertEqual(frontend.repo, "hr-tool-frontend")
        self.assertEqual(
            frontend.local_path, "/home/folium/Documents/HR-Tool/hr-tool-frontend"
        )
        self.assertEqual(frontend.author, "Volcann")
        self.assertEqual(
            frontend.full_name, "folium-hr-management-tool/hr-tool-frontend"
        )

    def test_lazy_reviewer_with_project_json_target(self):
        """Verify lazy-reviewer reuse using the project.json HR-Tool repo config."""
        projects = GitHubClient.load_projects("project.json")
        backend_cfg = next(p for p in projects if p.category == "Backend")

        fake_sha = "e" * 40
        fake_meta = metadata()
        fake_meta["headRefOid"] = fake_sha
        fake_meta["number"] = 350
        fake_meta["title"] = "feat: leave management"
        runner = FakeRunner(
            json_results=[
                fake_meta,
                [gql_page(head=fake_sha)],
            ],
            byte_results=[
                b"diff --git a/backend.py b/backend.py\n+import hr\n",
            ],
            text_results=[
                "Checked out\n",
                "https://github.com/folium-hr-management-tool/hr-tool-backend/pull/350#issuecomment-1\n",
            ],
        )

        client = GitHubClient(
            backend_cfg.full_name,
            local_repo_path=self.temp_dir.name,
            runner=runner,
            temp_dir=self.temp_dir.name,
        )

        meta = client.fetch_pr_metadata(350)
        self.assertEqual(meta["number"], 350)
        self.assertEqual(meta["title"], "feat: leave management")

        diff = client.fetch_pr_diff(350)
        self.assertIn("+import hr", diff)

        checkout_res = client.checkout_pr_branch(350)
        self.assertIn("Checked out", checkout_res)

        comment_res = client.post_pr_comment(350, "Automated review summary")
        self.assertIn("issuecomment-1", comment_res)

    def test_worked_task_rest_client_mock_tests(self):
        """Verify GitHubClient executes all 5 workedTask REST mock tests identically."""
        # 1. test_get_user_commits_ignores_merge_commits
        client = GitHubClient(token="mock_token", prefer_cli=False)

        fake_commits = [
            {
                "sha": "111111111111",
                "commit": {
                    "message": "feat: implement permission check for admin endpoints",
                    "author": {"name": "Volcann", "date": "2026-09-11T14:00:00Z"},
                },
                "author": {"login": "Volcann"},
                "html_url": "https://github.com/org/repo/commit/1111111",
            },
            {
                "sha": "222222222222",
                "commit": {
                    "message": "Merge pull request #340 from dev/fix",
                    "author": {"name": "Volcann", "date": "2026-09-11T15:00:00Z"},
                },
                "author": {"login": "Volcann"},
                "html_url": "https://github.com/org/repo/commit/2222222",
            },
        ]

        with patch.object(client, "_rest_get", return_value=fake_commits):
            commits = client.get_user_commits_for_date(
                "org", "repo", "Volcann", date(2026, 9, 11)
            )

        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].sha, "111111111111")
        self.assertEqual(
            commits[0].headline, "feat: implement permission check for admin endpoints"
        )

        # 2. test_get_user_prs_for_date
        fake_search = {
            "items": [
                {
                    "number": 348,
                    "title": "HMT-258 | Add search and natural sorting to device mappings",
                    "body": "Added search and natural sorting to device-user listings.",
                    "user": {"login": "Volcann"},
                    "state": "OPEN",
                    "html_url": "https://github.com/org/repo/pull/348",
                    "created_at": "2026-09-11T10:00:00Z",
                    "head": {"ref": "feature/HMT-258"},
                }
            ]
        }

        with patch.object(client, "_rest_get", return_value=fake_search):
            prs = client.get_user_prs_for_date(
                "org", "repo", "Volcann", date(2026, 9, 11)
            )

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].number, 348)
        self.assertTrue(prs[0].title.startswith("HMT-258"))
        self.assertTrue(prs[0].is_own)

        # 3. test_get_pr_details
        fake_pr_data = {
            "number": 359,
            "title": "MB-228: Payroll run",
            "body": "Summary of payroll run changes.",
            "user": {"login": "OtherDev"},
            "state": "OPEN",
            "html_url": "https://github.com/org/repo/pull/359",
            "created_at": "2026-09-15T10:00:00Z",
            "head": {"ref": "feat/payroll"},
        }

        fake_pr_commits = [
            {
                "sha": "fd3cfbc1234",
                "commit": {
                    "message": "Timesheet Attendance (HTM-228): Excluded soft-deleted users"
                },
                "author": {"login": "Volcann"},
            }
        ]

        def mock_get(endpoint: str, *args, **kwargs):
            if endpoint.endswith("/commits"):
                return fake_pr_commits
            return fake_pr_data

        with patch.object(client, "_rest_get", side_effect=mock_get):
            pr = client.get_pr_details("org", "repo", 359)

        self.assertIsNotNone(pr)
        self.assertEqual(pr.number, 359)
        self.assertEqual(pr.author_login, "OtherDev")
        self.assertEqual(len(pr.commits), 1)
        self.assertEqual(pr.commits[0].author_login, "Volcann")

        # 4. test_get_user_reviewed_prs_for_date
        fake_search_reviewed = {
            "items": [
                {
                    "number": 359,
                    "title": "MB-228: Payroll run",
                    "html_url": "https://github.com/org/repo/pull/359",
                }
            ]
        }

        fake_reviews = [
            {
                "user": {"login": "Volcann"},
                "state": "APPROVED",
                "submitted_at": "2026-09-16T12:30:00Z",
            },
            {
                "user": {"login": "SomeoneElse"},
                "state": "COMMENTED",
                "submitted_at": "2026-09-16T09:00:00Z",
            },
        ]

        def mock_reviews_get(endpoint: str, *args, **kwargs):
            if "reviews" in endpoint:
                return fake_reviews
            return fake_search_reviewed

        with patch.object(client, "_rest_get", side_effect=mock_reviews_get):
            reviews = client.get_user_reviewed_prs_for_date(
                "org", "repo", "Volcann", date(2026, 9, 16)
            )

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].pr_number, 359)
        self.assertEqual(reviews[0].state, "APPROVED")

        # 5. test_get_pr_user_comments
        fake_comments = [
            {
                "id": 1,
                "user": {"login": "Volcann"},
                "created_at": "2026-09-23T15:00:00Z",
                "body": "I have fully tested from FE no breaking changes.",
            },
            {
                "id": 2,
                "user": {"login": "OtherDev"},
                "created_at": "2026-09-23T16:00:00Z",
                "body": "LGTM from backend side.",
            },
        ]

        with patch.object(client, "_rest_get", return_value=fake_comments):
            comments = client.get_pr_user_comments(
                "org", "repo", 387, "Volcann", date(2026, 9, 23), use_cache=False
            )

        self.assertEqual(len(comments), 1)
        self.assertEqual(
            comments[0], "I have fully tested from FE no breaking changes."
        )

    def test_worked_task_collector_mutations(self):
        """Verify PullRequestItem, CommitItem, and ReviewItem support workedTask collector mutations."""
        from ghtoolkit import (
            CommitInfo,
            CommitItem,
            PullRequestInfo,
            PullRequestItem,
            ReviewInfo,
            ReviewItem,
        )

        commit = CommitItem({"sha": "1234567890abcdef", "message": "feat: test"})
        self.assertEqual(commit.short_sha, "1234567")
        commit.short_sha = "abcdef1"
        self.assertEqual(commit.short_sha, "abcdef1")
        self.assertTrue(isinstance(commit, CommitInfo))

        pr = PullRequestItem({"number": 100, "title": "Test PR", "body": "old body"})
        self.assertTrue(isinstance(pr, PullRequestInfo))

        # Test workedTask collector mutations
        pr.body = "new body"
        self.assertEqual(pr.body, "new body")

        pr.head_ref = "feat/new"
        self.assertEqual(pr.head_ref, "feat/new")

        pr.commits = [commit]
        self.assertEqual(len(pr.commits), 1)

        pr.author_commits = [commit]
        self.assertEqual(len(pr.author_commits), 1)

        pr.project_name = "HR-Tool"
        self.assertEqual(pr.project_name, "HR-Tool")

        pr.category = "Backend"
        self.assertEqual(pr.category, "Backend")

        pr.is_own = True
        self.assertTrue(pr.is_own)

        pr.bullets = ["bullet 1"]
        self.assertEqual(pr.bullets, ["bullet 1"])

        # ReviewItem mutations
        review = ReviewItem({"pr_number": 100, "state": "COMMENTED"})
        self.assertTrue(isinstance(review, ReviewInfo))
        review.project_name = "HR-Tool"
        review.category = "Backend"
        review.comments = ["LGTM"]
        review.review_bullets = ["bullet A"]
        self.assertEqual(review.project_name, "HR-Tool")
        self.assertEqual(review.comments, ["LGTM"])
        self.assertEqual(review.review_bullets, ["bullet A"])

    def test_lazy_reviewer_standalone_functions_and_inline_reviews(self):
        """Verify lazy-reviewer can import and call standalone top-level functions directly."""
        from ghtoolkit import (
            checkout_pr_branch,
            create_pull_request_review,
            fetch_pr_diff,
            fetch_pr_metadata,
            post_pr_comment,
        )

        fake_sha = "d" * 40
        fake_meta = metadata()
        fake_meta["number"] = 42
        fake_meta["headRefOid"] = fake_sha

        runner = FakeRunner(
            json_results=[
                fake_meta,
                [gql_page(head=fake_sha)],
                {"id": 888},
            ],
            byte_results=[b"diff --git a/x.py b/x.py\n+x=1\n"],
            text_results=[
                "Branch checked out\n",
                "https://github.com/org/repo/issues/comments/88\n",
            ],
        )

        client_inst = GitHubClient(runner=runner, temp_dir=self.temp_dir.name)
        with patch("ghtoolkit.github_client.GitHubClient", return_value=client_inst):
            meta = fetch_pr_metadata("org/repo", 42)
            self.assertEqual(meta["number"], 42)

            diff = fetch_pr_diff("org/repo", 42)
            self.assertIn("+x=1", diff)

            checkout_res = checkout_pr_branch(
                "org/repo", 42, local_repo_path=self.temp_dir.name
            )
            self.assertTrue(checkout_res)

            post_res = post_pr_comment("org/repo", 42, "Comment content")
            self.assertTrue(post_res)

            # Test inline comment without side (defaults to RIGHT)
            inline = [{"path": "x.py", "line": 5, "body": "fix line"}]
            rev_res = create_pull_request_review("org/repo", 42, fake_sha, inline)
            self.assertEqual(rev_res["id"], 888)

    def test_pr_alias_package_import(self):
        """Verify ghtoolkit.pr package alias is importable and matches pull_request."""
        import ghtoolkit.pr as pr_pkg
        import ghtoolkit.pull_request as pull_request_pkg

        self.assertIs(pr_pkg.PullRequestService, pull_request_pkg.PullRequestService)
        self.assertIs(pr_pkg.ReviewService, pull_request_pkg.ReviewService)
        self.assertEqual(pr_pkg.SUMMARY_FIELDS, pull_request_pkg.SUMMARY_FIELDS)


if __name__ == "__main__":
    unittest.main()
