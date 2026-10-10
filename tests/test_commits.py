import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ghtoolkit import GhCommandError, GhResponseError, GitHubClient

from tests.helpers import OTHER_SHA, PATCH, SHA, FakeRunner, commit, rest_pr


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def client(self, runner, timezone="UTC"):
        return GitHubClient(
            "acme/widget",
            runner=runner,
            timezone=timezone,
            temp_dir=self.directory.name,
        )

    def test_list_returns_only_hash_and_full_message(self):
        runner = FakeRunner(json_results=[[[commit()], [commit(OTHER_SHA)]]])
        result = self.client(runner).get_commits()
        self.assertEqual([item["hash"] for item in result], [SHA, OTHER_SHA])
        self.assertEqual(set(result[0]), {"hash", "message"})
        self.assertEqual(result[0]["message"], "Fix the bug\n\nPreserve this body.")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_empty_list_stays_empty(self):
        self.assertEqual(self.client(FakeRunner(json_results=[[[]]])).get_commits(), [])

    def test_date_is_committer_date_and_half_open(self):
        records = [
            commit(SHA, "2026-10-03T00:00:00Z"),
            commit(OTHER_SHA, "2026-10-04T00:00:00Z"),
            commit("c" * 40, "2026-10-02T23:59:59Z"),
        ]
        runner = FakeRunner(json_results=[[records]])
        result = self.client(runner).get_user_commits_for_date(
            "alice", "2026-10-03", branch="feature/a"
        )
        self.assertEqual([item["hash"] for item in result], [SHA])
        params = parse_qs(urlsplit(runner.calls[0][1][1]).query)
        self.assertEqual(params["author"], ["alice"])
        self.assertEqual(params["sha"], ["feature/a"])
        self.assertEqual(params["since"], ["2026-10-02T23:59:59Z"])

    def test_karachi_commit_date(self):
        runner = FakeRunner(
            json_results=[
                [
                    [
                        commit(SHA, "2026-10-02T19:00:00Z"),
                        commit(OTHER_SHA, "2026-10-03T19:00:00Z"),
                    ]
                ]
            ]
        )
        self.assertEqual(
            self.client(runner, "Asia/Karachi").get_commits(date="2026-10-03")[0][
                "hash"
            ],
            SHA,
        )

    def test_limit_is_applied_after_date_filter(self):
        runner = FakeRunner(
            json_results=[[[commit(SHA, "2026-10-02T23:59:59Z"), commit(OTHER_SHA)]]]
        )
        result = self.client(runner).get_commits(date="2026-10-03", limit=1)
        self.assertEqual(result[0]["hash"], OTHER_SHA)

    def test_default_branch_is_not_assumed_to_be_main(self):
        runner = FakeRunner(json_results=[[[]]])
        self.client(runner).get_commits()
        self.assertNotIn("sha", parse_qs(urlsplit(runner.calls[0][1][1]).query))

    def test_invalid_limit_is_a_caller_error(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.client(FakeRunner()).get_commits(limit=limit)

    def test_missing_metadata_is_a_response_error(self):
        for item in (
            {"sha": SHA},
            {"sha": SHA, "commit": {}},
            {"commit": {"message": "x"}},
        ):
            with self.subTest(item=item), self.assertRaises(GhResponseError):
                self.client(FakeRunner(json_results=[[[item]]])).get_commits()

    def test_duplicate_commits_are_not_returned_twice(self):
        result = self.client(
            FakeRunner(json_results=[[[commit()], [commit()]]])
        ).get_commits()
        self.assertEqual(len(result), 1)

    def test_commit_details_merge_file_pages(self):
        pages = [
            {**commit(), "files": [{"filename": "a.py"}], "stats": {"total": 2}},
            {**commit(), "files": [{"filename": "b.py"}], "stats": {"total": 2}},
        ]
        result = self.client(FakeRunner(json_results=[pages])).get_commit_details(SHA)
        self.assertEqual(
            [item["filename"] for item in result["files"]], ["a.py", "b.py"]
        )
        self.assertFalse(result["filesMayBeTruncated"])
        self.assertEqual(result["stats"], {"total": 2})

    def test_commit_details_report_possible_server_cap(self):
        item = {**commit(), "files": [{"filename": str(i)} for i in range(3000)]}
        self.assertTrue(
            self.client(FakeRunner(json_results=[[item]])).get_commit_details(SHA)[
                "filesMayBeTruncated"
            ]
        )

    def test_moving_commit_ref_during_pagination_raises(self):
        pages = [{**commit(), "files": []}, {**commit(OTHER_SHA), "files": []}]
        with self.assertRaises(GhResponseError):
            self.client(FakeRunner(json_results=[pages])).get_commit_details("main")

    def test_ref_is_encoded_as_one_url_path_segment(self):
        runner = FakeRunner(byte_results=[PATCH])
        artifact = self.client(runner).get_commit_diff("feature/a?b=c")
        self.assertEqual(artifact.diff_path.read_bytes(), PATCH)
        self.assertIn("commits/feature%2Fa%3Fb%3Dc", runner.calls[0][1][1])
        self.assertIn("Accept: application/vnd.github.diff", runner.calls[0][1])

    def test_fetch_commit_diff_returns_text_and_preserves_files(self):
        text = self.client(FakeRunner(byte_results=[PATCH])).fetch_commit_diff(SHA)
        self.assertEqual(text, PATCH.decode())
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.diff"))), 1)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.md"))), 1)

    def test_associated_pull_requests_have_distinct_merged_state(self):
        runner = FakeRunner(
            json_results=[
                [[rest_pr(state="closed", merged=True), rest_pr(8, "closed")]]
            ]
        )
        result = self.client(runner).get_pulls_for_commit(SHA)
        self.assertEqual([item["state"] for item in result], ["MERGED", "CLOSED"])
        self.assertEqual([item["number"] for item in result], [7, 8])

    def test_auth_alias_is_resolved_before_commit_filtering(self):
        runner = FakeRunner(json_results=[{"login": "alice"}, [[]]])
        self.client(runner).get_commits(author="@me")
        self.assertEqual(runner.calls[0][1][1], "user")
        self.assertEqual(
            parse_qs(urlsplit(runner.calls[1][1][1]).query)["author"], ["alice"]
        )

    def test_command_failure_is_not_converted_to_no_commits(self):
        runner = FakeRunner(json_results=[GhCommandError(1, "network failed")])
        with self.assertRaises(GhCommandError):
            self.client(runner).get_commits()
