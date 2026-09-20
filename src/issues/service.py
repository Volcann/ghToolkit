from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from ..api import GhAPI
from ..validation import nonempty, positive_number


class IssueService:
    def __init__(self, api: GhAPI):
        self._api = api

    def comments(self, number: int) -> list[dict[str, Any]]:
        return self._api.list(f"issues/{positive_number(number)}/comments")

    def post_pr_comment(self, number: int, body: str) -> str:
        positive_number(number)
        nonempty(body, "body")
        with tempfile.TemporaryDirectory(prefix="ghtoolkit-comment-") as directory:
            path = Path(directory) / "body.md"
            with path.open("xb") as handle:
                os.chmod(path, 0o600)
                handle.write(body.encode("utf-8"))
            return self._api.runner.run(
                "pr",
                "comment",
                str(number),
                "--repo",
                self._api.repository.cli_name,
                "--body-file",
                str(path),
            ).strip()
