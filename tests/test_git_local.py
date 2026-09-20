from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghtoolkit import run_git_command
from ghtoolkit.git_local import (
    get_local_commit_branch,
    get_local_commit_pull_requests,
    get_local_commits_for_date,
    get_local_pr_details,
    get_local_prs_for_date,
    get_local_reviewed_prs_for_date,
    is_merge_commit_message,
)


class GitLocalTests(unittest.TestCase):
    def test_is_merge_commit_message(self):
        self.assertTrue(is_merge_commit_message("Merge pull request #12 from dev"))
        self.assertTrue(is_merge_commit_message("Merge branch 'feature' into main"))
        self.assertFalse(is_merge_commit_message("feat: add new user profile endpoint"))

    def test_run_git_command_missing_dir(self):
        self.assertIsNone(run_git_command(["status"], "/nonexistent/path/here"))

    @patch("ghtoolkit.git_local.run_git_command")
    def test_get_local_commits_for_date(self, mock_git):
        raw_log = "a" * 40 + "\x1ffeat: my commit\x1fdescription\x1fMohsin Ali\x1fmohsin@test.com\x1f2026-10-09T14:00:00+00:00\x1e"
        mock_git.side_effect = [
            raw_log,  # log
            "  feature/auth\n* main\n",  # branch --contains
            "src/auth.py\n",  # diff-tree
        ]

        commits = get_local_commits_for_date(
            "/dummy/repo", "volcann", date(2026, 10, 9)
        )
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].sha, "a" * 40)
        self.assertEqual(commits[0].headline, "feat: my commit")
        self.assertEqual(commits[0].branch, "feature/auth")
        self.assertEqual(commits[0].files, ["src/auth.py"])

    @patch("ghtoolkit.git_local.run_git_command")
    def test_get_local_prs_for_date(self, mock_git):
        h = "b" * 40
        raw_merge_log = f"{h}\x1fMerge pull request #45 from feature/payments\x1fPayment gateway additions\x1fMohsin Ali\x1fmohsin@test.com\x1f2026-10-09T15:00:00+00:00"
        mock_git.side_effect = [
            raw_merge_log,  # merge log
            "c" * 40 + "\x1fAdd stripe handler\x1f\x1fMohsin Ali\x1fmohsin@test.com\x1f2026-10-09T14:30:00+00:00",  # pr commits
        ]

        prs = get_local_prs_for_date("/dummy/repo", "volcann", date(2026, 10, 9))
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].number, 45)
        self.assertEqual(prs[0].state, "MERGED")
        self.assertEqual(prs[0].head_ref, "feature/payments")
        self.assertEqual(len(prs[0].commits), 1)

    @patch("ghtoolkit.git_local.run_git_command")
    def test_get_local_commit_pull_requests(self, mock_git):
        mock_git.side_effect = [
            "c123456 Merge pull request #77 from bugfix\n",  # ancestry
        ]
        prs = get_local_commit_pull_requests("/dummy/repo", "sha123")
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], 77)

    @patch("ghtoolkit.git_local.run_git_command")
    def test_get_local_commit_branch(self, mock_git):
        mock_git.return_value = "  main\n  feature/JIRA-101-auth\n"
        branch = get_local_commit_branch("/dummy/repo", "sha123", commit_message="JIRA-101: fix auth")
        self.assertEqual(branch, "feature/JIRA-101-auth")


if __name__ == "__main__":
    unittest.main()
