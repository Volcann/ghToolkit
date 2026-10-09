from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ..core.api import GhAPI
from ..commit.service import CommitSummary
from ..core.dates import DateInput, DateWindow
from ..storage.diffs import DiffResult, DiffStore
from ..core.errors import GhResponseError
from ..core.validation import (
    nonempty,
    object_list,
    object_value,
    positive_number,
    result_limit,
)

DateField = Literal["created", "updated", "merged", "closed"]
SUMMARY_FIELDS = (
    "number",
    "title",
    "state",
    "url",
    "author",
    "createdAt",
    "updatedAt",
    "mergedAt",
    "closedAt",
    "isDraft",
    "headRefName",
    "baseRefName",
)
DETAIL_FIELDS = SUMMARY_FIELDS + (
    "body",
    "headRefOid",
    "baseRefOid",
    "additions",
    "deletions",
    "changedFiles",
    "mergeable",
    "mergeStateStatus",
    "reviewDecision",
    "mergedBy",
    "mergeCommit",
    "commits",
)
DATE_FIELDS = {
    "created": "createdAt",
    "updated": "updatedAt",
    "merged": "mergedAt",
    "closed": "closedAt",
}
PR_COMMITS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      commits(first: 100, after: $endCursor) {
        totalCount
        nodes {
          commit {
            oid message messageHeadline messageBody authoredDate committedDate
            authors(first: 100) {
              totalCount
              nodes { name email user { login } }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


def summarize_rest_pr(item: dict[str, Any]) -> dict[str, Any]:
    state = "MERGED" if item.get("merged_at") else str(item.get("state", "")).upper()
    if state not in {"OPEN", "CLOSED", "MERGED"}:
        raise GhResponseError("GitHub returned an unknown pull request state")
    user = item.get("user")
    author = {"login": user.get("login")} if isinstance(user, dict) else None
    return {
        "number": item["number"],
        "title": item["title"],
        "state": state,
        "url": item.get("html_url"),
        "author": author,
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "mergedAt": item.get("merged_at"),
        "closedAt": item.get("closed_at"),
        "isDraft": item.get("draft", False),
        "headRefName": (item.get("head") or {}).get("ref"),
        "baseRefName": (item.get("base") or {}).get("ref"),
    }


class PullRequestService:
    def __init__(self, api: GhAPI, diffs: DiffStore, timezone: str):
        self._api = api
        self._diffs = diffs
        self._timezone = timezone

    def list(
        self,
        *,
        date: DateInput | None = None,
        date_field: DateField = "created",
        state: str = "all",
        author: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        result_limit(limit)
        if date_field not in DATE_FIELDS:
            raise ValueError("date_field must be created, updated, merged, or closed")
        state = nonempty(state, "state").lower()
        if state not in {"all", "open", "closed", "merged"}:
            raise ValueError("state must be all, open, closed, or merged")
        window = DateWindow.for_date(date, self._timezone) if date is not None else None
        args = [
            "pr",
            "list",
            "--repo",
            self._api.repository.cli_name,
            "--state",
            state,
            "--limit",
            "1000",
            "--json",
            ",".join(SUMMARY_FIELDS),
        ]
        if author is not None:
            args.extend(["--author", nonempty(author, "author")])
        if window:
            args.extend(["--search", window.search(date_field)])
        records = object_list(self._api.runner.run_json(*args), "pull request list")
        if len(records) >= 1000:
            records = [
                summarize_rest_pr(item)
                for item in self._api.list(
                    "pulls", {"state": "all", "sort": "created", "direction": "desc"}
                )
            ]
        selected: dict[int, dict[str, Any]] = {}
        for item in records:
            if item.get("state") not in {"OPEN", "CLOSED", "MERGED"}:
                raise GhResponseError("GitHub returned an unknown pull request state")
            if state != "all" and item["state"] != state.upper():
                continue
            if window and not window.contains(item.get(DATE_FIELDS[date_field])):
                continue
            login = (item.get("author") or {}).get("login")
            if author is not None and (login or "").casefold() != author.casefold():
                continue
            number = item.get("number")
            if isinstance(number, bool) or not isinstance(number, int):
                raise GhResponseError("Pull request response is missing its number")
            selected[number] = {field: item.get(field) for field in SUMMARY_FIELDS}
        result = sorted(
            selected.values(), key=lambda item: item["number"], reverse=True
        )
        return result[:limit]

    def metadata(self, number: int) -> dict[str, Any]:
        positive_number(number)
        metadata = object_value(
            self._api.runner.run_json(
                "pr",
                "view",
                str(number),
                "--repo",
                self._api.repository.cli_name,
                "--json",
                ",".join(DETAIL_FIELDS),
            ),
            "pull request metadata",
        )
        head = metadata.get("headRefOid")
        if not isinstance(head, str) or not head:
            raise GhResponseError("Pull request metadata is missing headRefOid")
        metadata["commits"] = self.commit_details(number, expected_head=head)
        return metadata

    def commit_details(
        self, number: int, *, expected_head: str | None = None
    ) -> list[dict[str, Any]]:
        positive_number(number)
        repo = self._api.repository
        pages = self._api.graphql_pages(
            PR_COMMITS_QUERY, {"owner": repo.owner, "name": repo.name, "number": number}
        )
        commits: dict[str, dict[str, Any]] = {}
        expected_count: int | None = None
        for page in pages:
            data = object_value(page.get("data"), "GraphQL data")
            repository = object_value(data.get("repository"), "GraphQL repository")
            pull = object_value(repository.get("pullRequest"), "GraphQL pull request")
            head = pull.get("headRefOid")
            if not isinstance(head, str) or not head:
                raise GhResponseError("GraphQL pull request is missing headRefOid")
            if expected_head is None:
                expected_head = head
            if head != expected_head:
                raise GhResponseError(
                    "Pull request head changed during retrieval; retry"
                )
            connection = object_value(pull.get("commits"), "pull request commits")
            count = connection.get("totalCount")
            if not isinstance(count, int) or (
                expected_count is not None and count != expected_count
            ):
                raise GhResponseError(
                    "Pull request commit count changed during retrieval; retry"
                )
            expected_count = count
            for node in object_list(
                connection.get("nodes"), "pull request commit nodes"
            ):
                commit = dict(object_value(node.get("commit"), "pull request commit"))
                authors = object_value(commit.get("authors"), "commit authors")
                author_nodes = object_list(authors.get("nodes"), "commit author nodes")
                commit["authors"] = [
                    {
                        "name": author.get("name"),
                        "email": author.get("email"),
                        "login": (author.get("user") or {}).get("login"),
                    }
                    for author in author_nodes
                ]
                commit["authorsTruncated"] = len(author_nodes) < authors.get(
                    "totalCount", len(author_nodes)
                )
                if not isinstance(commit.get("oid"), str) or not isinstance(
                    commit.get("message"), str
                ):
                    raise GhResponseError(
                        "Pull request commit is missing its SHA or message"
                    )
                commits[commit["oid"]] = commit
        if expected_count is None or len(commits) != expected_count:
            raise GhResponseError(
                "GitHub did not return the complete pull request commit list"
            )
        return list(commits.values())

    def commits(self, number: int) -> list[CommitSummary]:
        return [
            {"hash": item["oid"], "message": item["message"]}
            for item in self.commit_details(number)
        ]

    def files(self, number: int) -> list[dict[str, Any]]:
        return self._api.list(f"pulls/{positive_number(number)}/files")

    def diff(self, number: int) -> DiffResult:
        positive_number(number)
        raw = self._api.runner.run_bytes(
            "pr",
            "diff",
            str(number),
            "--repo",
            self._api.repository.cli_name,
            "--color",
            "never",
        )
        return self._diffs.save(self._api.repository.cli_name, "pr", str(number), raw)

    def fetch_diff(self, number: int) -> str:
        positive_number(number)
        return self._api.runner.run(
            "pr",
            "diff",
            str(number),
            "--repo",
            self._api.repository.cli_name,
            "--color",
            "never",
        )

    def get_state(self, number: int) -> str | None:
        positive_number(number)
        try:
            data = self._api.runner.run_json(
                "pr",
                "view",
                str(number),
                "--repo",
                self._api.repository.cli_name,
                "--json",
                "state",
            )
            if isinstance(data, dict):
                return data.get("state")
        except Exception:
            pass
        return None

    def checkout(self, number: int, local_repo_path: str | Path) -> str:
        positive_number(number)
        return self._api.runner.run(
            "pr",
            "checkout",
            str(number),
            "--repo",
            self._api.repository.cli_name,
            cwd=local_repo_path,
        )
