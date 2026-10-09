from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass, field
from typing import Any

from .commits import CommitItem


@dataclass
class PullRequestInfo(metaclass=ABCMeta):
    number: int
    title: str
    author_login: str = ""
    state: str = "OPEN"
    created_at: str = ""
    url: str = ""
    body: str = ""
    head_ref: str = ""
    base_ref: str = ""
    is_draft: bool = False
    is_own: bool = True
    commits: list[Any] = field(default_factory=list)
    author_commits: list[Any] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    labels: list[Any] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    comments: list[Any] = field(default_factory=list)
    category: str = "Backend"
    repo_name: str = ""
    project_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "author_login": self.author_login,
            "state": self.state,
            "created_at": self.created_at,
            "url": self.url,
            "body": self.body,
            "head_ref": self.head_ref,
            "base_ref": self.base_ref,
            "is_draft": self.is_draft,
            "is_own": self.is_own,
            "commits": list(self.commits),
            "author_commits": list(self.author_commits),
            "files_changed": list(self.files_changed),
            "labels": list(self.labels),
            "bullets": list(self.bullets),
            "comments": list(self.comments),
            "category": self.category,
            "repo_name": self.repo_name,
            "project_name": self.project_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PullRequestInfo:
        return cls(
            number=int(data.get("number", 0)),
            title=data.get("title", ""),
            author_login=(
                data.get("author_login") or (data.get("author") or {}).get("login", "")
                if isinstance(data.get("author"), dict)
                else data.get("author_login", "")
            ),
            state=data.get("state", "OPEN"),
            created_at=data.get("created_at") or data.get("createdAt", ""),
            url=data.get("url", ""),
            body=data.get("body", ""),
            head_ref=data.get("headRefName") or data.get("head_ref", ""),
            base_ref=data.get("baseRefName") or data.get("base_ref", ""),
            is_draft=bool(data.get("isDraft") or data.get("is_draft", False)),
            is_own=bool(data.get("is_own", True)),
            commits=data.get("commits", []),
            author_commits=data.get("author_commits", []),
            files_changed=data.get("files_changed", data.get("files", [])),
            labels=data.get("labels", []),
            bullets=data.get("bullets", []),
            comments=data.get("comments", []),
            category=data.get("category", "Backend"),
            repo_name=data.get("repo_name", ""),
            project_name=data.get("project_name", ""),
        )


class PullRequestItem(dict):
    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    @property
    def number(self) -> int:
        return int(self.get("number", 0))

    @number.setter
    def number(self, value: int) -> None:
        self["number"] = int(value)

    @property
    def title(self) -> str:
        return self.get("title", "")

    @title.setter
    def title(self, value: str) -> None:
        self["title"] = value

    @property
    def author_login(self) -> str:
        if "author_login" in self:
            return self["author_login"]
        auth = self.get("author")
        if isinstance(auth, dict):
            return auth.get("login", "")
        return str(auth or "")

    @author_login.setter
    def author_login(self, value: str) -> None:
        self["author_login"] = value

    @property
    def state(self) -> str:
        return str(self.get("state", "OPEN")).upper()

    @state.setter
    def state(self, value: str) -> None:
        self["state"] = value

    @property
    def created_at(self) -> str:
        return self.get("created_at") or self.get("createdAt", "")

    @created_at.setter
    def created_at(self, value: str) -> None:
        self["created_at"] = value

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
    def updated_at(self) -> str:
        return self.get("updatedAt") or self.get("updated_at", "")

    @updated_at.setter
    def updated_at(self, value: str) -> None:
        self["updated_at"] = value

    @property
    def merged_at(self) -> str | None:
        return self.get("mergedAt") or self.get("merged_at")

    @merged_at.setter
    def merged_at(self, value: str | None) -> None:
        self["merged_at"] = value

    @property
    def closed_at(self) -> str | None:
        return self.get("closedAt") or self.get("closed_at")

    @closed_at.setter
    def closed_at(self, value: str | None) -> None:
        self["closed_at"] = value

    @property
    def head_ref(self) -> str:
        return self.get("headRefName") or self.get("head_ref", "")

    @head_ref.setter
    def head_ref(self, value: str) -> None:
        self["head_ref"] = value

    @property
    def base_ref(self) -> str:
        return self.get("baseRefName") or self.get("base_ref", "")

    @base_ref.setter
    def base_ref(self, value: str) -> None:
        self["base_ref"] = value

    @property
    def is_draft(self) -> bool:
        return bool(self.get("isDraft") or self.get("is_draft", False))

    @is_draft.setter
    def is_draft(self, value: bool) -> None:
        self["is_draft"] = bool(value)

    @property
    def is_own(self) -> bool:
        return bool(self.get("is_own", True))

    @is_own.setter
    def is_own(self, value: bool) -> None:
        self["is_own"] = bool(value)

    @property
    def commits(self) -> list[Any]:
        raw = self.setdefault("commits", [])
        return [
            CommitItem(c)
            if isinstance(c, dict) and not isinstance(c, CommitItem)
            else c
            for c in raw
        ]

    @commits.setter
    def commits(self, value: list[Any]) -> None:
        self["commits"] = [
            CommitItem(c)
            if isinstance(c, dict) and not isinstance(c, CommitItem)
            else c
            for c in value
        ]

    @property
    def author_commits(self) -> list[Any]:
        raw = self.setdefault("author_commits", [])
        return [
            CommitItem(c)
            if isinstance(c, dict) and not isinstance(c, CommitItem)
            else c
            for c in raw
        ]

    @author_commits.setter
    def author_commits(self, value: list[Any]) -> None:
        self["author_commits"] = [
            CommitItem(c)
            if isinstance(c, dict) and not isinstance(c, CommitItem)
            else c
            for c in value
        ]

    @property
    def files_changed(self) -> list[str]:
        return self.get("files_changed", self.get("files", []))

    @files_changed.setter
    def files_changed(self, value: list[str]) -> None:
        self["files_changed"] = value

    @property
    def files(self) -> list[str]:
        return self.get("files", self.get("files_changed", []))

    @files.setter
    def files(self, value: list[str]) -> None:
        self["files"] = value

    @property
    def labels(self) -> list[Any]:
        return self.get("labels", [])

    @labels.setter
    def labels(self, value: list[Any]) -> None:
        self["labels"] = value

    @property
    def bullets(self) -> list[str]:
        return self.setdefault("bullets", [])

    @bullets.setter
    def bullets(self, value: list[str]) -> None:
        self["bullets"] = value

    @property
    def comments(self) -> list[Any]:
        return self.setdefault("comments", [])

    @comments.setter
    def comments(self, value: list[Any]) -> None:
        self["comments"] = value

    @property
    def category(self) -> str:
        return self.get("category", "Backend")

    @category.setter
    def category(self, value: str) -> None:
        self["category"] = value

    @property
    def repo_name(self) -> str:
        return self.get("repo_name", "")

    @repo_name.setter
    def repo_name(self, value: str) -> None:
        self["repo_name"] = value

    @property
    def project_name(self) -> str:
        return self.get("project_name", "")

    @project_name.setter
    def project_name(self, value: str) -> None:
        self["project_name"] = value

    def to_info(self) -> PullRequestInfo:
        return PullRequestInfo.from_dict(self)


PullRequestInfo.register(PullRequestItem)
