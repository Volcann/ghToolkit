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
class ProjectConfig:
    """Configuration for a repository project to track or audit."""

    owner: str
    repo: str
    name: str = "HR-Tool"
    category: str = "Backend"
    author: str = "Volcann"
    local_path: str = ""
    enabled: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "owner": self.owner,
            "repo": self.repo,
            "author": self.author,
            "local_path": self.local_path,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        return cls(
            name=data.get("name") or data.get("project_name") or "HR-Tool",
            category=data.get("category")
            or (
                "Frontend"
                if "frontend" in (data.get("repo") or "").lower()
                else "Backend"
            ),
            owner=data.get("owner", ""),
            repo=data.get("repo", ""),
            author=data.get("author", "Volcann"),
            local_path=data.get("local_path", ""),
            enabled=data.get("enabled", True),
        )


@dataclass
class CommitInfo(metaclass=ABCMeta):
    """Details of a single git commit."""

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
    """Dictionary subclass providing transparent attribute access for CommitInfo compatibility."""

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
    def url(self) -> str:
        return self.get("url") or self.get("html_url", "")

    @url.setter
    def url(self, value: str) -> None:
        self["url"] = value

    @property
    def branch(self) -> str | None:
        return self.get("branch")

    @branch.setter
    def branch(self, value: str | None) -> None:
        self["branch"] = value

    @property
    def pr_number(self) -> int | None:
        return self.get("pr_number")

    @pr_number.setter
    def pr_number(self, value: int | None) -> None:
        self["pr_number"] = value

    @property
    def files(self) -> list[str]:
        return self.get("files", [])

    @files.setter
    def files(self, value: list[str]) -> None:
        self["files"] = value

    def to_info(self) -> CommitInfo:
        return CommitInfo.from_dict(self)


@dataclass
class PullRequestInfo(metaclass=ABCMeta):
    """Details of a GitHub pull request."""

    number: int
    title: str
    body: str = ""
    author_login: str = ""
    state: str = "OPEN"
    url: str = ""
    created_at: str = ""
    updated_at: str = ""
    merged_at: str | None = None
    closed_at: str | None = None
    head_ref: str = ""
    base_ref: str = ""
    is_draft: bool = False
    is_own: bool = True
    commits: list[CommitInfo] = field(default_factory=list)
    author_commits: list[CommitInfo] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    category: str = "Backend"
    project_name: str = "HR-Tool"
    repo_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "author_login": self.author_login,
            "state": self.state,
            "url": self.url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "merged_at": self.merged_at,
            "closed_at": self.closed_at,
            "head_ref": self.head_ref,
            "base_ref": self.base_ref,
            "is_draft": self.is_draft,
            "is_own": self.is_own,
            "commits": [
                c.to_dict() if hasattr(c, "to_dict") else c for c in self.commits
            ],
            "author_commits": [
                c.to_dict() if hasattr(c, "to_dict") else c for c in self.author_commits
            ],
            "files_changed": list(self.files_changed),
            "labels": list(self.labels),
            "bullets": list(self.bullets),
            "comments": list(self.comments),
            "category": self.category,
            "project_name": self.project_name,
            "repo_name": self.repo_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PullRequestInfo:
        author_val = data.get("author_login")
        if not author_val:
            auth_obj = data.get("author") or data.get("user")
            if isinstance(auth_obj, dict):
                author_val = auth_obj.get("login", "")
            elif isinstance(auth_obj, str):
                author_val = auth_obj

        commits_raw = data.get("commits", [])
        commits_parsed = [
            CommitInfo.from_dict(c) if isinstance(c, dict) else c for c in commits_raw
        ]

        files_raw = data.get("files_changed") or data.get("files", [])
        files_list = [
            f.get("path") if isinstance(f, dict) else str(f) for f in files_raw
        ]

        labels_raw = data.get("labels", [])
        labels_list = [
            lbl.get("name") if isinstance(lbl, dict) else str(lbl) for lbl in labels_raw
        ]

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            author_login=author_val or "",
            state=str(data.get("state", "OPEN")).upper(),
            url=data.get("url") or data.get("html_url", ""),
            created_at=data.get("created_at") or data.get("createdAt", ""),
            updated_at=data.get("updated_at") or data.get("updatedAt", ""),
            merged_at=data.get("merged_at") or data.get("mergedAt"),
            closed_at=data.get("closed_at") or data.get("closedAt"),
            head_ref=data.get("head_ref") or data.get("headRefName", ""),
            base_ref=data.get("base_ref") or data.get("baseRefName", ""),
            is_draft=bool(data.get("is_draft") or data.get("isDraft", False)),
            is_own=bool(data.get("is_own", True)),
            commits=commits_parsed,
            author_commits=[],
            files_changed=files_list,
            labels=labels_list,
            bullets=data.get("bullets", []),
            comments=data.get("comments", []),
            category=data.get("category", "Backend"),
            project_name=data.get("project_name") or data.get("name", "HR-Tool"),
            repo_name=data.get("repo_name", ""),
        )


class PullRequestItem(dict):
    """Dictionary subclass providing transparent attribute access for PullRequestInfo compatibility."""

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
        return self.get("number", 0)

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
    def body(self) -> str:
        return self.get("body", "")

    @body.setter
    def body(self, value: str) -> None:
        self["body"] = value

    @property
    def author_login(self) -> str:
        if "author_login" in self:
            return self["author_login"]
        auth = self.get("author") or self.get("user")
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
    def url(self) -> str:
        return self.get("url") or self.get("html_url", "")

    @url.setter
    def url(self, value: str) -> None:
        self["url"] = value

    @property
    def created_at(self) -> str:
        return self.get("createdAt") or self.get("created_at", "")

    @created_at.setter
    def created_at(self, value: str) -> None:
        self["created_at"] = value

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


@dataclass
class ReviewInfo(metaclass=ABCMeta):
    """Details of a submitted pull request review."""

    pr_number: int
    pr_title: str
    reviewer: str
    state: str  # APPROVED, COMMENTED, CHANGES_REQUESTED, REVIEWED
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
    """Dictionary subclass providing transparent attribute access for ReviewInfo compatibility."""

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


CommitInfo.register(CommitItem)
PullRequestInfo.register(PullRequestItem)
ReviewInfo.register(ReviewItem)
