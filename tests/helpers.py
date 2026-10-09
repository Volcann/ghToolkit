from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any

SHA = "a" * 40
OTHER_SHA = "b" * 40
PATCH = b"diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old()\n+new()\n"


class FakeRunner:
    def __init__(self, *, json_results=(), byte_results=(), text_results=()):
        super().__init__()
        self.json_results = deque(json_results)
        self.byte_results = deque(byte_results)
        self.text_results = deque(text_results)
        self.calls: list[tuple[str, tuple[str, ...], dict[str, Any]]] = []

    def _take(self, kind, queue, args, kwargs):
        self.calls.append((kind, args, kwargs))
        if not queue:
            raise AssertionError(f"Unexpected {kind} call: {args}")
        result = queue.popleft()
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)

    def run_json(self, *args, **kwargs):
        return self._take("json", self.json_results, args, kwargs)

    def run_bytes(self, *args, **kwargs):
        return self._take("bytes", self.byte_results, args, kwargs)

    def run(self, *args, **kwargs):
        return self._take("text", self.text_results, args, kwargs)


def commit(
    sha=SHA,
    timestamp="2026-10-03T12:00:00Z",
    message="Fix the bug\n\nPreserve this body.",
):
    return {
        "sha": sha,
        "commit": {
            "message": message,
            "author": {"date": "2026-10-01T00:00:00Z"},
            "committer": {"date": timestamp},
        },
    }


def pr(number=7, state="OPEN", timestamp="2026-10-03T12:00:00Z", author="alice"):
    return {
        "number": number,
        "title": f"Pull request {number}",
        "state": state,
        "url": f"https://github.com/acme/widget/pull/{number}",
        "author": {"login": author},
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "mergedAt": timestamp if state == "MERGED" else None,
        "closedAt": timestamp if state in {"CLOSED", "MERGED"} else None,
        "headRefName": "feature",
        "baseRefName": "main",
        "isDraft": False,
    }


def rest_pr(number=7, state="open", timestamp="2026-10-03T12:00:00Z", merged=False):
    return {
        "number": number,
        "title": f"Pull request {number}",
        "state": state,
        "html_url": f"https://github.com/acme/widget/pull/{number}",
        "user": {"login": "alice"},
        "created_at": timestamp,
        "updated_at": timestamp,
        "merged_at": timestamp if merged else None,
        "closed_at": timestamp if state == "closed" else None,
        "head": {"ref": "feature"},
        "base": {"ref": "main"},
        "draft": False,
    }


def gql_commit(sha=SHA):
    return {
        "commit": {
            "oid": sha,
            "message": "Fix bug\n\nDetails",
            "messageHeadline": "Fix bug",
            "messageBody": "Details",
            "authoredDate": "2026-10-02T10:00:00Z",
            "committedDate": "2026-10-03T12:00:00Z",
            "authors": {
                "totalCount": 1,
                "nodes": [
                    {
                        "name": "Alice",
                        "email": "alice@example.test",
                        "user": {"login": "alice"},
                    }
                ],
            },
        }
    }


def gql_page(nodes=None, total=1, head=SHA):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": head,
                    "commits": {
                        "totalCount": total,
                        "nodes": nodes if nodes is not None else [gql_commit()],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }
    }


def metadata():
    return {
        **pr(),
        "body": "Description",
        "headRefOid": SHA,
        "baseRefOid": OTHER_SHA,
        "changedFiles": 1,
        "additions": 1,
        "deletions": 1,
        "commits": [],
    }


def review(
    identifier=1, author="alice", timestamp="2026-10-03T12:00:00Z", body="Looks good"
):
    return {
        "id": identifier,
        "user": {"login": author},
        "submitted_at": timestamp,
        "state": "APPROVED",
        "body": body,
        "commit_id": SHA,
    }
