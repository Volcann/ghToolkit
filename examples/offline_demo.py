from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ghtoolkit import GitHubClient, GhRunner

SHA = "0123456789abcdef0123456789abcdef01234567"
PATCH = b"diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('old')\n+print('new')\n"


class OfflineRunner(GhRunner):
    def run_json(
        self, *args: str, input_text: str | None = None, cwd: str | Path | None = None
    ) -> Any:
        if args[:2] == ("pr", "list"):
            return [
                {
                    "number": 7,
                    "title": "Synthetic example pull request",
                    "state": "MERGED",
                    "url": "https://github.com/example/demo/pull/7",
                    "author": {"login": "alice"},
                    "createdAt": "2026-10-03T08:00:00Z",
                    "updatedAt": "2026-10-03T12:00:00Z",
                    "mergedAt": "2026-10-03T12:00:00Z",
                    "closedAt": "2026-10-03T12:00:00Z",
                    "isDraft": False,
                    "headRefName": "example",
                    "baseRefName": "main",
                }
            ]
        if args[0] == "api" and args[1].startswith("repos/example/demo/commits?"):
            return [
                [
                    {
                        "sha": SHA,
                        "commit": {
                            "message": "Update the example output",
                            "committer": {"date": "2026-10-03T08:00:00Z"},
                        },
                    }
                ]
            ]
        raise AssertionError(f"No offline fixture for {args}")

    def run_bytes(
        self, *args: str, input_data: bytes | None = None, cwd: str | Path | None = None
    ) -> bytes:
        if args[:2] == ("pr", "diff") or (args[0] == "api" and "/commits/" in args[1]):
            return PATCH
        raise AssertionError(f"No offline fixture for {args}")


def main() -> None:
    client = GitHubClient("example/demo", runner=OfflineRunner(), temp_dir="temp")
    print("Synthetic offline data; no GitHub requests are made.")
    print(
        json.dumps(
            {
                "commits": client.get_commits(date="2026-10-03"),
                "pull_requests": client.get_prs(date="2026-10-03"),
            },
            indent=2,
        )
    )
    for artifact in (client.get_commit_diff(SHA), client.get_pr_diff(7)):
        print(artifact.diff_path)
        print(artifact.markdown_path)


if __name__ == "__main__":
    main()
