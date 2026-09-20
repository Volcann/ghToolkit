from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import quote

from ..api import GhAPI
from ..dates import DateInput, DateWindow
from ..diff_store import DiffResult, DiffStore
from ..errors import GhResponseError
from ..validation import nonempty, object_list, object_value, result_limit


class CommitSummary(TypedDict):
    hash: str
    message: str


class CommitService:
    def __init__(self, api: GhAPI, diffs: DiffStore, timezone: str):
        self._api = api
        self._diffs = diffs
        self._timezone = timezone

    def list(
        self,
        *,
        date: DateInput | None = None,
        author: str | None = None,
        branch: str | None = None,
        limit: int | None = None,
    ) -> list[CommitSummary]:
        result_limit(limit)
        params: dict[str, str | int] = {}
        window = DateWindow.for_date(date, self._timezone) if date is not None else None
        if window:
            params.update(window.commit_parameters())
        if author is not None:
            params["author"] = nonempty(author, "author")
        if branch is not None:
            params["sha"] = nonempty(branch, "branch")
        result: dict[str, CommitSummary] = {}
        for item in self._api.list("commits", params):
            commit = object_value(item.get("commit"), "commit metadata")
            if window:
                committer = object_value(commit.get("committer"), "commit committer")
                if not window.contains(committer.get("date")):
                    continue
            sha, message = item.get("sha"), commit.get("message")
            if not isinstance(sha, str) or not isinstance(message, str):
                raise GhResponseError("Commit response is missing its SHA or message")
            result[sha] = {"hash": sha, "message": message}
        return list(result.values())[:limit]

    def details(self, ref: str) -> dict[str, Any]:
        endpoint = f"commits/{quote(nonempty(ref, 'ref'), safe='')}"
        pages = self._api.pages(endpoint)
        if not pages:
            raise GhResponseError("GitHub returned no commit details")
        records = [object_value(page, "commit details") for page in pages]
        result = dict(records[0])
        sha = result.get("sha")
        if not isinstance(sha, str) or any(page.get("sha") != sha for page in records):
            raise GhResponseError(
                "Commit reference changed during pagination; retry with a SHA"
            )
        result["files"] = [
            file
            for record in records
            for file in object_list(record.get("files"), "commit files")
        ]
        result["filesMayBeTruncated"] = len(result["files"]) >= 3000
        return result

    def diff(self, ref: str) -> DiffResult:
        endpoint = f"commits/{quote(nonempty(ref, 'ref'), safe='')}"
        return self._diffs.save(
            self._api.repository.cli_name, "commit", ref, self._api.diff(endpoint)
        )

    def pulls(self, ref: str) -> list[dict[str, Any]]:
        endpoint = f"commits/{quote(nonempty(ref, 'ref'), safe='')}/pulls"
        return self._api.list(endpoint)
