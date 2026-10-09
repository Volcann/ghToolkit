from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass, field
from typing import Any, TypedDict


class CommitSummary(TypedDict):
    hash: str
    message: str


@dataclass
class CommitInfo(metaclass=ABCMeta):
    sha: str
    message: str
    author_name: str = ""
    author_login: str = ""
    author_email: str = ""
    date: str = ""
    url: str = ""
    branch: str | None = None
    pr_number: int | None = None
    files: list[str] = field(default_factory=list)

    @property
    def short_sha(self) -> str:
        return self.sha[:7] if self.sha else ""

    @property
    def hash(self) -> str:
        return self.sha

    @property
    def headline(self) -> str:
        if not self.message:
            return ""
        return self.message.strip().splitlines()[0]

    @property
    def body(self) -> str:
        if not self.message:
            return ""
        lines = self.message.strip().splitlines()
        return "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "hash": self.sha,
            "message": self.message,
            "author_name": self.author_name,
            "author_login": self.author_login,
            "author_email": self.author_email,
            "date": self.date,
            "url": self.url,
            "branch": self.branch,
            "pr_number": self.pr_number,
            "files": list(self.files),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommitInfo:
        sha = data.get("sha") or data.get("hash") or data.get("oid") or ""
        msg = data.get("message") or data.get("messageHeadline") or ""
        return cls(
            sha=sha,
            message=msg,
            author_name=data.get("author_name", ""),
            author_login=data.get("author_login", ""),
            author_email=data.get("author_email", ""),
            date=data.get("date") or data.get("committedDate") or "",
            url=data.get("url", ""),
            branch=data.get("branch"),
            pr_number=data.get("pr_number"),
            files=data.get("files", []),
        )


class CommitItem(dict):
    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    @property
    def sha(self) -> str:
        return self.get("sha") or self.get("hash") or self.get("oid") or ""

    @sha.setter
    def sha(self, value: str) -> None:
        self["sha"] = value

    @property
    def hash(self) -> str:
        return self.sha

    @hash.setter
    def hash(self, value: str) -> None:
        self["sha"] = value
        self["hash"] = value

    @property
    def short_sha(self) -> str:
        if "short_sha" in self:
            return self["short_sha"]
        s = self.sha
        return s[:7] if s else ""

    @short_sha.setter
    def short_sha(self, value: str) -> None:
        self["short_sha"] = value

    @property
    def message(self) -> str:
        return self.get("message") or self.get("messageHeadline") or ""

    @message.setter
    def message(self, value: str) -> None:
        self["message"] = value

    @property
    def headline(self) -> str:
        if "headline" in self:
            return self["headline"]
        msg = self.message
        return msg.strip().splitlines()[0] if msg else ""

    @headline.setter
    def headline(self, value: str) -> None:
        self["headline"] = value

    @property
    def body(self) -> str:
        if "body" in self:
            return self["body"]
        msg = self.message
        if not msg:
            return ""
        lines = msg.strip().splitlines()
        return "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    @body.setter
    def body(self, value: str) -> None:
        self["body"] = value

    @property
    def author_name(self) -> str:
        if "author_name" in self:
            return self["author_name"]
        auth = self.get("author")
        if isinstance(auth, dict):
            return auth.get("name", "")
        authors = self.get("authors")
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            return authors[0].get("name", "")
        return str(auth or "")

    @author_name.setter
    def author_name(self, value: str) -> None:
        self["author_name"] = value

    @property
    def author_login(self) -> str:
        if "author_login" in self:
            return self["author_login"]
        auth = self.get("author")
        if isinstance(auth, dict):
            return auth.get("login", auth.get("name", ""))
        authors = self.get("authors")
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            return authors[0].get("login", authors[0].get("name", ""))
        return self.author_name

    @author_login.setter
    def author_login(self, value: str) -> None:
        self["author_login"] = value

    @property
    def author_email(self) -> str:
        if "author_email" in self:
            return self["author_email"]
        auth = self.get("author")
        if isinstance(auth, dict):
            return auth.get("email", "")
        authors = self.get("authors")
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            return authors[0].get("email", "")
        return ""

    @author_email.setter
    def author_email(self, value: str) -> None:
        self["author_email"] = value

    @property
    def date(self) -> str:
        return (
            self.get("date")
            or self.get("committedDate")
            or self.get("authoredDate")
            or ""
        )

    @date.setter
    def date(self, value: str) -> None:
        self["date"] = value

    @property
    def pr_number(self) -> int | None:
        return self.get("pr_number")

    @pr_number.setter
    def pr_number(self, value: int | None) -> None:
        self["pr_number"] = value

    @property
    def branch(self) -> str | None:
        return self.get("branch")

    @branch.setter
    def branch(self, value: str | None) -> None:
        self["branch"] = value

    @property
    def files(self) -> list[str]:
        return self.get("files", self.get("files_changed", []))

    @files.setter
    def files(self, value: list[str]) -> None:
        self["files"] = value

    @property
    def url(self) -> str:
        return self.get("url", "")

    @url.setter
    def url(self, value: str) -> None:
        self["url"] = value

    def to_info(self) -> CommitInfo:
        return CommitInfo.from_dict(self)


CommitInfo.register(CommitItem)
