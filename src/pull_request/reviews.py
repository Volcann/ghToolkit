from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal, NotRequired, Sequence, TypedDict

from ..api import GhAPI
from ..dates import DateInput, DateWindow, parse_timestamp
from ..validation import nonempty, positive_number


class InlineReviewComment(TypedDict):
    path: str
    line: int
    side: Literal["LEFT", "RIGHT"]
    body: str
    start_line: NotRequired[int]
    start_side: NotRequired[Literal["LEFT", "RIGHT"]]


class ReviewService:
    def __init__(self, api: GhAPI, timezone: str):
        self._api = api
        self._timezone = timezone

    def list(self, number: int) -> list[dict[str, Any]]:
        return self._api.list(f"pulls/{positive_number(number)}/reviews")

    def inline_comments(self, number: int) -> list[dict[str, Any]]:
        return self._api.list(f"pulls/{positive_number(number)}/comments")

    def for_user_date(
        self, author: str, date: DateInput, *, pr_numbers: Sequence[int] | None = None
    ) -> list[dict[str, Any]]:
        nonempty(author, "author")
        window = DateWindow.for_date(date, self._timezone)
        if pr_numbers is None:
            candidates = self._api.list(
                "pulls", {"state": "all", "sort": "created", "direction": "desc"}
            )
            numbers = [
                item["number"]
                for item in candidates
                if parse_timestamp(item["created_at"]) < window.end
                and parse_timestamp(item["updated_at"]) >= window.start
            ]
        else:
            numbers = [positive_number(number) for number in pr_numbers]
        result = []
        for number in dict.fromkeys(numbers):
            for review in self.list(number):
                login = (review.get("user") or {}).get("login") or ""
                if login.casefold() == author.casefold() and window.contains(
                    review.get("submitted_at")
                ):
                    result.append({**review, "pr_number": number})
        return sorted(
            result, key=lambda item: (parse_timestamp(item["submitted_at"]), item["id"])
        )

    def create(
        self,
        number: int,
        commit_id: str,
        comments: Sequence[InlineReviewComment],
        *,
        body: str = "",
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        positive_number(number)
        if not isinstance(commit_id, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", commit_id
        ):
            raise ValueError("commit_id must be a full 40-character commit SHA")
        if not isinstance(body, str):
            raise TypeError("body must be a string")
        if event not in {"COMMENT", "APPROVE", "REQUEST_CHANGES"}:
            raise ValueError("event must be COMMENT, APPROVE, or REQUEST_CHANGES")
        validated = [self._validate_comment(comment) for comment in comments]
        if not validated and not body.strip():
            raise ValueError("A review must contain comments or a nonempty body")
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "event": event,
            "comments": validated,
        }
        if body:
            payload["body"] = body
        return self._api.post(f"pulls/{number}/reviews", payload)

    @staticmethod
    def _validate_comment(comment: InlineReviewComment) -> dict[str, Any]:
        if not isinstance(comment, dict):
            raise TypeError("Each inline comment must be a dictionary")
        required = {"path", "line", "side", "body"}
        allowed = required | {"start_line", "start_side"}
        if not required <= comment.keys() or not comment.keys() <= allowed:
            raise ValueError("Inline comments require path, line, side, and body")
        path = nonempty(comment["path"], "comment.path")
        if (
            PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or "\\" in path
        ):
            raise ValueError("comment.path must be a repository-relative POSIX path")
        positive_number(comment["line"], "comment.line")
        nonempty(comment["body"], "comment.body")
        if comment["side"] not in {"LEFT", "RIGHT"}:
            raise ValueError("comment.side must be LEFT or RIGHT")
        if "start_line" in comment:
            positive_number(comment["start_line"], "comment.start_line")
            if comment.get("start_side") not in {"LEFT", "RIGHT"}:
                raise ValueError("Multiline comments require start_side")
            if (
                comment["start_side"] == comment["side"]
                and comment["start_line"] > comment["line"]
            ):
                raise ValueError("start_line cannot exceed line on the same side")
        elif "start_side" in comment:
            raise ValueError("start_side requires start_line")
        return dict(comment)
