from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict


class InlineReviewComment(TypedDict):
    path: str
    line: int
    side: Literal["LEFT", "RIGHT"]
    body: str
    start_line: NotRequired[int]
    start_side: NotRequired[Literal["LEFT", "RIGHT"]]


@dataclass
class ReviewInfo(metaclass=ABCMeta):
    pr_number: int
    pr_title: str
    reviewer: str
    state: str
    submitted_at: str = ""
    url: str = ""
    body: str = ""
    comments: list[str] = field(default_factory=list)
    review_bullets: list[str] = field(default_factory=list)
    project_name: str = ""
    category: str = "Backend"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_number": self.pr_number,
            "pr_title": self.pr_title,
            "reviewer": self.reviewer,
            "state": self.state,
            "submitted_at": self.submitted_at,
            "url": self.url,
            "body": self.body,
            "comments": list(self.comments),
            "review_bullets": list(self.review_bullets),
            "project_name": self.project_name,
            "category": self.category,
        }


class ReviewItem(dict):
    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    @property
    def pr_number(self) -> int:
        return self.get("pr_number", 0)

    @pr_number.setter
    def pr_number(self, value: int) -> None:
        self["pr_number"] = int(value)

    @property
    def pr_title(self) -> str:
        return self.get("pr_title") or self.get("title", "")

    @pr_title.setter
    def pr_title(self, value: str) -> None:
        self["pr_title"] = value

    @property
    def reviewer(self) -> str:
        if "reviewer" in self:
            return self["reviewer"]
        user = self.get("user")
        if isinstance(user, dict):
            return user.get("login", "")
        return str(user or "")

    @reviewer.setter
    def reviewer(self, value: str) -> None:
        self["reviewer"] = value

    @property
    def state(self) -> str:
        return str(self.get("state", "COMMENTED")).upper()

    @state.setter
    def state(self, value: str) -> None:
        self["state"] = value

    @property
    def submitted_at(self) -> str:
        return self.get("submitted_at") or self.get("submittedAt", "")

    @submitted_at.setter
    def submitted_at(self, value: str) -> None:
        self["submitted_at"] = value

    @property
    def url(self) -> str:
        return self.get("url") or self.get("html_url", "")

    @url.setter
    def url(self, value: str) -> None:
        self["url"] = value

    @property
    def body(self) -> str:
        return self.get("body", "")

    @body.setter
    def body(self, value: str) -> None:
        self["body"] = value

    @property
    def comments(self) -> list[str]:
        return self.setdefault("comments", [])

    @comments.setter
    def comments(self, value: list[str]) -> None:
        self["comments"] = value

    @property
    def review_bullets(self) -> list[str]:
        return self.setdefault("review_bullets", [])

    @review_bullets.setter
    def review_bullets(self, value: list[str]) -> None:
        self["review_bullets"] = value

    @property
    def project_name(self) -> str:
        return self.get("project_name", "")

    @project_name.setter
    def project_name(self, value: str) -> None:
        self["project_name"] = value

    @property
    def category(self) -> str:
        return self.get("category", "Backend")

    @category.setter
    def category(self, value: str) -> None:
        self["category"] = value

    def to_info(self) -> ReviewInfo:
        return ReviewInfo(
            pr_number=self.pr_number,
            pr_title=self.pr_title,
            reviewer=self.reviewer,
            state=self.state,
            submitted_at=self.submitted_at,
            url=self.url,
            body=self.body,
            comments=self.comments,
            review_bullets=self.review_bullets,
            project_name=self.project_name,
            category=self.category,
        )


ReviewInfo.register(ReviewItem)
