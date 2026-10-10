import json
import tempfile
import unittest
from pathlib import Path

from ghtoolkit import GitHubClient

from tests.helpers import FakeRunner


class UnifiedClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_pr_diff(self):
        runner = FakeRunner(byte_results=[b"diff --git a/test b/test\n+new\n"])
        client = GitHubClient("owner/repo", runner=runner, temp_dir=self.temp_dir.name)
        dest = Path(self.temp_dir.name) / "output.diff"
        saved = client.save_pr_diff(10, dest)
        self.assertTrue(saved.exists())
        self.assertEqual(saved.read_text(), "diff --git a/test b/test\n+new\n")

    def test_load_projects_file(self):
        projects_path = Path(self.temp_dir.name) / "projects.json"
        projects_data = [
            {
                "owner": "org1",
                "repo": "backend",
                "name": "API Service",
                "author": "volcann",
            },
            {
                "owner": "org2",
                "repo": "frontend",
                "name": "Web Client",
                "author": "alice",
            },
        ]
        projects_path.write_text(json.dumps(projects_data))

        projects = GitHubClient.load_projects(projects_path)
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0].name, "API Service")
        self.assertEqual(projects[1].owner, "org2")

    def test_author_alias_registration_on_client(self):
        client = GitHubClient(
            "owner/repo", runner=FakeRunner(), temp_dir=self.temp_dir.name
        )
        self.assertFalse(client.is_author_match("custom_lead", login="lead_dev_handle"))
        client.register_author_alias("custom_lead", ["lead_dev_handle"])
        self.assertTrue(client.is_author_match("custom_lead", login="lead_dev_handle"))

    def test_get_all_prs(self):
        runner = FakeRunner(
            json_results=[
                [
                    {"number": 1, "author": {"login": "dev1"}},
                    {"number": 2, "author": {"login": "dev2"}},
                ]
            ]
        )
        client = GitHubClient("owner/repo", runner=runner, temp_dir=self.temp_dir.name)
        prs = client.get_all_prs(state="all", limit=100)
        self.assertEqual(len(prs), 2)
        self.assertEqual(prs[0]["number"], 1)

    def test_get_pr_state(self):
        runner = FakeRunner(json_results=[{"state": "CLOSED"}])
        client = GitHubClient("owner/repo", runner=runner, temp_dir=self.temp_dir.name)
        state = client.get_pr_state(42)
        self.assertEqual(state, "CLOSED")


if __name__ == "__main__":
    unittest.main()
