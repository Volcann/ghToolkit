import tempfile
import unittest
from pathlib import Path

from ghtoolkit import GitHubClient, GhResponseError
from tests.helpers import (
    FakeRunner,
    PATCH,
    SHA,
    OTHER_SHA,
    gql_commit,
    gql_page,
    metadata,
    pr,
    rest_pr,
    review,
)


class PullRequestTests(unittest.TestCase):
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

    def test_default_list_includes_all_states_and_numbers(self):
        runner = FakeRunner(json_results=[[pr(1), pr(2, "MERGED"), pr(3, "CLOSED")]])
        result = self.client(runner).get_prs()
        self.assertEqual([item["number"] for item in result], [3, 2, 1])
        self.assertEqual(
            {item["state"] for item in result}, {"OPEN", "MERGED", "CLOSED"}
        )
        args = runner.calls[0][1]
        self.assertEqual(args[args.index("--state") + 1], "all")
        self.assertNotIn("commits", result[0])
        self.assertNotIn("body", result[0])
        self.assertNotIn("--search", args)

    def test_exact_created_date(self):
        runner = FakeRunner(
            json_results=[
                [
                    pr(1, timestamp="2026-10-03T00:00:00Z"),
                    pr(2, timestamp="2026-10-04T00:00:00Z"),
                ]
            ]
        )
        result = self.client(runner).get_prs(date="2026-10-03")
        self.assertEqual([item["number"] for item in result], [1])
        args = runner.calls[0][1]
        self.assertEqual(args[args.index("--search") + 1], "created:2026-10-03")

    def test_karachi_date_is_filtered_after_broad_utc_search(self):
        runner = FakeRunner(
            json_results=[
                [
                    pr(1, timestamp="2026-10-02T19:00:00Z"),
                    pr(2, timestamp="2026-10-03T19:00:00Z"),
                ]
            ]
        )
        result = self.client(runner, "Asia/Karachi").get_prs(date="2026-10-03")
        self.assertEqual([item["number"] for item in result], [1])
        self.assertIn("created:2026-10-02..2026-10-03", runner.calls[0][1])

    def test_date_fields_have_distinct_semantics(self):
        for field, key in (
            ("updated", "updatedAt"),
            ("merged", "mergedAt"),
            ("closed", "closedAt"),
        ):
            with self.subTest(field=field):
                item = pr(1, "MERGED", "2026-10-01T00:00:00Z")
                item[key] = "2026-10-03T12:00:00Z"
                runner = FakeRunner(json_results=[[item]])
                result = self.client(runner).get_prs(
                    date="2026-10-03", date_field=field
                )
                self.assertEqual(len(result), 1)
                self.assertIn(f"{field}:2026-10-03", runner.calls[0][1])

    def test_author_filter_and_state_are_rechecked(self):
        runner = FakeRunner(
            json_results=[[pr(1, "MERGED"), pr(2, "MERGED", author="bob"), pr(3)]]
        )
        result = self.client(runner).get_user_prs_for_date(
            "ALICE", "2026-10-03", state="MERGED"
        )
        self.assertEqual([item["number"] for item in result], [1])
        self.assertIn("ALICE", runner.calls[0][1])

    def test_closed_excludes_merged(self):
        runner = FakeRunner(json_results=[[pr(1, "MERGED"), pr(2, "CLOSED")]])
        self.assertEqual(self.client(runner).get_prs(state="closed")[0]["number"], 2)

    def test_invalid_arguments_do_not_run_commands(self):
        for kwargs in (
            {"state": "draft"},
            {"date_field": "reviewed"},
            {"limit": 0},
            {"date": "today"},
        ):
            runner = FakeRunner()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.client(runner).get_prs(**kwargs)
            self.assertEqual(runner.calls, [])

    def test_limit_is_applied_after_filtering(self):
        runner = FakeRunner(
            json_results=[[pr(1), pr(2, timestamp="2026-10-04T00:00:00Z"), pr(3)]]
        )
        result = self.client(runner).get_prs(date="2026-10-03", limit=1)
        self.assertEqual([item["number"] for item in result], [3])

    def test_saturated_cli_list_falls_back_to_paginated_api(self):
        runner = FakeRunner(
            json_results=[
                [pr()] * 1000,
                [
                    [rest_pr(1)],
                    [rest_pr(2, "closed", merged=True), rest_pr(3, "closed")],
                ],
            ]
        )
        result = self.client(runner).get_prs(date="2026-10-03", state="merged")
        self.assertEqual([item["number"] for item in result], [2])
        self.assertEqual(len(runner.calls), 2)
        self.assertIn("--paginate", runner.calls[1][1])

    def test_unknown_state_is_not_silently_returned(self):
        with self.assertRaises(GhResponseError):
            self.client(FakeRunner(json_results=[[pr(state="MYSTERY")]])).get_prs()

    def test_pr_diff_is_separate_from_metadata_and_disables_color(self):
        runner = FakeRunner(byte_results=[PATCH])
        artifact = self.client(runner).get_pr_diff(7)
        self.assertEqual(artifact.diff_path.read_bytes(), PATCH)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0][1][-2:], ("--color", "never"))
        self.assertTrue(artifact.markdown_path.is_file())

    def test_fetch_pr_diff_is_compatible_with_text_parsers(self):
        runner = FakeRunner(byte_results=[PATCH])
        self.assertEqual(self.client(runner).fetch_pr_diff(7), PATCH.decode())
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.diff"))), 1)

    def test_pr_numbers_must_be_positive_integers(self):
        for value in (True, 0, -1, "7", 7.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client(FakeRunner()).get_pr_diff(value)

    def test_metadata_has_full_commit_projection(self):
        runner = FakeRunner(json_results=[metadata(), [gql_page()]])
        result = self.client(runner).fetch_pr_metadata(7)
        self.assertEqual(result["number"], 7)
        self.assertEqual(result["author"]["login"], "alice")
        self.assertEqual(result["commits"][0]["oid"], SHA)
        self.assertEqual(result["commits"][0]["authors"][0]["login"], "alice")
        self.assertIn("authoredDate", result["commits"][0])
        self.assertNotIn("date", result["commits"][0]["authors"][0])
        self.assertIn("commits", runner.calls[0][1][-1].split(","))

    def test_pr_commit_list_returns_only_hash_and_message(self):
        result = self.client(FakeRunner(json_results=[[gql_page()]])).get_pr_commits(7)
        self.assertEqual(result, [{"hash": SHA, "message": "Fix bug\n\nDetails"}])

    def test_pr_commits_paginate_beyond_rest_250_cap(self):
        nodes = [gql_commit(f"{i:040x}") for i in range(301)]
        pages = [
            gql_page(nodes[:100], total=301),
            gql_page(nodes[100:200], total=301),
            gql_page(nodes[200:300], total=301),
            gql_page(nodes[300:], total=301),
        ]
        result = self.client(FakeRunner(json_results=[pages])).get_pr_commits(7)
        self.assertEqual(len(result), 301)

    def test_partial_graphql_result_is_an_error(self):
        with self.assertRaises(GhResponseError):
            self.client(FakeRunner(json_results=[[gql_page(total=2)]])).get_pr_commits(
                7
            )

    def test_head_change_while_fetching_metadata_is_an_error(self):
        with self.assertRaises(GhResponseError):
            self.client(
                FakeRunner(json_results=[metadata(), [gql_page(head=OTHER_SHA)]])
            ).fetch_pr_metadata(7)

    def test_unlinked_author_is_preserved_without_login(self):
        node = gql_commit()
        node["commit"]["authors"]["nodes"][0]["user"] = None
        node["commit"]["authors"]["totalCount"] = 2
        result = self.client(
            FakeRunner(json_results=[metadata(), [gql_page([node])]])
        ).fetch_pr_metadata(7)
        self.assertIsNone(result["commits"][0]["authors"][0]["login"])
        self.assertTrue(result["commits"][0]["authorsTruncated"])

    def test_full_details_aggregate_files_reviews_and_all_comment_kinds(self):
        issue = {"id": 2, "body": "Discussion", "created_at": "2026-10-03T12:00:00Z"}
        inline = {"id": 3, "body": "Inline", "path": "example.py", "line": 1}
        runner = FakeRunner(
            json_results=[
                metadata(),
                [gql_page()],
                [[{"filename": "example.py"}]],
                [[review()]],
                [[issue]],
                [[inline]],
            ]
        )
        result = self.client(runner).get_pr_details(7)
        self.assertEqual(result["files"][0]["filename"], "example.py")
        self.assertFalse(result["filesTruncated"])
        self.assertEqual(result["reviews"][0]["state"], "APPROVED")
        self.assertEqual(
            {item["kind"] for item in result["comments"]}, {"issue", "inline", "review"}
        )
        self.assertEqual(len(runner.calls), 6)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_server_file_truncation_is_explicit(self):
        details = metadata()
        details["changedFiles"] = 3001
        runner = FakeRunner(
            json_results=[
                details,
                [gql_page()],
                [[{"filename": "x"}]],
                [[]],
                [[]],
                [[]],
            ]
        )
        self.assertTrue(self.client(runner).get_pr_details(7)["filesTruncated"])

    def test_checkout_requires_local_path(self):
        with self.assertRaises(ValueError):
            self.client(FakeRunner()).checkout_pr_branch(7)

    def test_checkout_uses_configured_working_directory_without_force(self):
        runner = FakeRunner(text_results=["checked out\n"])
        client = GitHubClient(
            "acme/widget", runner=runner, local_repo_path=self.directory.name
        )
        self.assertEqual(client.checkout_pr_branch(7), "checked out\n")
        self.assertEqual(runner.calls[0][2]["cwd"], self.directory.name)
        self.assertNotIn("--force", runner.calls[0][1])
