from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

from .api import GhAPI, Repository
from .audit import (
    ProgressQueue,
    get_pr_state,
    scan_contributor_contributions,
    scan_foreign_pr,
)
from .comments import CommentCache, fetch_pr_user_comments
from .commit.service import CommitService, CommitSummary
from .dates import DateInput, DateWindow, parse_timestamp, resolve_timezone
from .diff_store import DiffResult, DiffStore
from .git_local import (
    get_local_commit_branch,
    get_local_commit_pull_requests,
    get_local_commits_for_date,
    get_local_pr_details,
    get_local_prs_for_date,
    get_local_reviewed_prs_for_date,
    run_git_command,
)
from .identity import AuthorRegistry, is_author_match, register_author_alias
from .issues.service import IssueService
from .models import (
    CommitInfo,
    CommitItem,
    InlineReviewComment,
    ProjectConfig,
    PullRequestInfo,
    PullRequestItem,
    ReviewInfo,
    ReviewItem,
)
from .pull_request.reviews import ReviewService
from .pull_request.service import DateField, PullRequestService, summarize_rest_pr
from .runner import GhRunner
from .validation import nonempty, positive_number


class GitHubClient:
    """Universal GitHub Client facade supporting CLI, API, GraphQL, and Local Git operations."""

    def __init__(
        self,
        repo: str | None = None,
        *,
        timeout: float | None = 30.0,
        timezone: str = "UTC",
        temp_dir: str | Path = "temp",
        local_repo_path: str | Path | None = None,
        runner: GhRunner | None = None,
    ):
        self._runner = runner if runner is not None else GhRunner(timeout=timeout)
        self._timezone = timezone
        resolve_timezone(timezone)
        self._temp_dir = temp_dir
        self._diffs = DiffStore(temp_dir)
        self._local_repo_path = local_repo_path
        self._author_registry = AuthorRegistry()

        if repo:
            repository = Repository.parse(repo)
            self._api = GhAPI(repository, self._runner)
            self._commits = CommitService(self._api, self._diffs, timezone)
            self._pulls = PullRequestService(self._api, self._diffs, timezone)
            self._issues = IssueService(self._api)
            self._reviews = ReviewService(self._api, timezone)
            self.repo = repository.cli_name
        else:
            self._api = None  # type: ignore[assignment]
            self._commits = None  # type: ignore[assignment]
            self._pulls = None  # type: ignore[assignment]
            self._issues = None  # type: ignore[assignment]
            self._reviews = None  # type: ignore[assignment]
            self.repo = ""

    def _ensure_repo(self, owner_or_repo: str | None = None, repo_name: str | None = None) -> GitHubClient:
        """Return a client configured for a specific repository if needed."""
        if owner_or_repo and repo_name:
            target = f"{owner_or_repo}/{repo_name}"
            if self._api and self._api.repository.full_name.casefold() == target.casefold():
                return self
            return GitHubClient(
                target,
                timezone=self._timezone,
                temp_dir=self._temp_dir,
                local_repo_path=self._local_repo_path,
                runner=self._runner,
            )
        if self._api is not None:
            return self
        raise ValueError("Repository is required. Pass 'owner/repo' to GitHubClient or to method.")

    @property
    def available(self) -> bool:
        return self._runner.available

    def version(self) -> str:
        return self._runner.run("version")

    # -------------------------------------------------------------------------
    # Identity & Aliases
    # -------------------------------------------------------------------------

    def register_author_alias(self, author: str, aliases: Sequence[str]) -> None:
        """Register custom aliases for a contributor."""
        self._author_registry.register(author, aliases)
        register_author_alias(author, aliases)

    def is_author_match(
        self,
        target_author: str,
        name: str = "",
        email: str = "",
        login: str = "",
    ) -> bool:
        """Check if author matches target contributor using aliases."""
        return self._author_registry.is_match(
            target_author, name=name, email=email, login=login
        )

    def _author(self, author: str | None) -> str | None:
        if author is None:
            return None
        nonempty(author, "author")
        if author == "@me":
            client = self._ensure_repo()
            return client._api.get_object("/user")["login"]
        return author

    # -------------------------------------------------------------------------
    # Commits
    # -------------------------------------------------------------------------

    def get_commits(
        self,
        *,
        date: DateInput | None = None,
        author: str | None = None,
        branch: str | None = None,
        limit: int | None = None,
    ) -> list[CommitSummary]:
        client = self._ensure_repo()
        return client._commits.list(
            date=date, author=client._author(author), branch=branch, limit=limit
        )

    def get_user_commits_for_date(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[CommitSummary]:
        """Fetch commits authored on `date`.

        Supports signatures:
          get_user_commits_for_date(author, date, branch=None, local_path=None)
          get_user_commits_for_date(owner, repo, author, date, local_path=None)
        """
        if len(args) >= 4:
            owner, repo, author, target_date = args[:4]
            client = self._ensure_repo(owner, repo)
        elif len(args) == 2:
            author, target_date = args
            client = self._ensure_repo()
        else:
            author = kwargs.get("author") or (args[0] if args else "")
            target_date = kwargs.get("date") or (args[1] if len(args) > 1 else "")
            client = self._ensure_repo()

        branch = kwargs.get("branch")
        local_path = kwargs.get("local_path") or client._local_repo_path

        # 1. Try local git repository if path exists
        if local_path and Path(local_path).is_dir():
            dt = target_date if isinstance(target_date, date) else date.fromisoformat(str(target_date)[:10])
            local_commits = get_local_commits_for_date(
                local_path, author, dt, registry=self._author_registry
            )
            if local_commits:
                return local_commits  # type: ignore[return-value]

        # 2. Fall back to standard get_commits
        return client.get_commits(date=target_date, author=author, branch=branch)

    def get_commit_details(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if len(args) >= 3:
            owner, repo, ref = args[:3]
            client = self._ensure_repo(owner, repo)
        elif len(args) == 2 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, ref = args[:2]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            ref = args[0] if args else kwargs.get("ref", "")
            client = self._ensure_repo()
        return client._commits.details(ref)

    def get_commit_diff(self, *args: Any, **kwargs: Any) -> DiffResult:
        if len(args) >= 3:
            owner, repo, ref = args[:3]
            client = self._ensure_repo(owner, repo)
        elif len(args) == 2 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, ref = args[:2]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            ref = args[0] if args else kwargs.get("ref", "")
            client = self._ensure_repo()
        return client._commits.diff(ref)

    def fetch_commit_diff(self, *args: Any, **kwargs: Any) -> str:
        return self.get_commit_diff(*args, **kwargs).text

    def get_pulls_for_commit(self, ref: str) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        return [summarize_rest_pr(item) for item in client._commits.pulls(ref)]

    def get_commit_pull_requests(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Find pull requests associated with a commit SHA.

        Supports:
          get_commit_pull_requests(commit_sha, local_path=None)
          get_commit_pull_requests(owner, repo, commit_sha, local_path=None)
        """
        if len(args) >= 3:
            owner, repo, commit_sha = args[:3]
            client = self._ensure_repo(owner, repo)
        else:
            commit_sha = args[0] if args else kwargs.get("commit_sha", "")
            client = self._ensure_repo()

        local_path = kwargs.get("local_path") or client._local_repo_path
        if local_path and Path(local_path).is_dir():
            local_prs = get_local_commit_pull_requests(local_path, commit_sha)
            if local_prs:
                return local_prs

        return client.get_pulls_for_commit(commit_sha)

    def get_commit_branch(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Find feature branch associated with a commit SHA.

        Supports:
          get_commit_branch(commit_sha, commit_message="", local_path=None)
          get_commit_branch(owner, repo, commit_sha, commit_message="", local_path=None)
        """
        if len(args) >= 3:
            owner, repo, commit_sha = args[:3]
            client = self._ensure_repo(owner, repo)
            commit_message = args[3] if len(args) > 3 else kwargs.get("commit_message", "")
        else:
            commit_sha = args[0] if args else kwargs.get("commit_sha", "")
            client = self._ensure_repo()
            commit_message = kwargs.get("commit_message", "")

        local_path = kwargs.get("local_path") or client._local_repo_path
        if local_path and Path(local_path).is_dir():
            return get_local_commit_branch(local_path, commit_sha, commit_message=commit_message)
        return "main"

    # -------------------------------------------------------------------------
    # Pull Requests
    # -------------------------------------------------------------------------

    def get_prs(
        self,
        *,
        date: DateInput | None = None,
        date_field: DateField = "created",
        state: str = "all",
        author: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        prs = client._pulls.list(
            date=date,
            date_field=date_field,
            state=state,
            author=client._author(author),
            limit=limit,
        )
        return [PullRequestItem(p) for p in prs]

    def get_user_prs_for_date(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch pull requests for `date`.

        Supports:
          get_user_prs_for_date(author, date, date_field="created", state="all", local_path=None)
          get_user_prs_for_date(owner, repo, author, date, local_path=None)
        """
        if len(args) >= 4:
            owner, repo, author, target_date = args[:4]
            client = self._ensure_repo(owner, repo)
        else:
            author = args[0] if args else kwargs.get("author", "")
            target_date = args[1] if len(args) > 1 else kwargs.get("date", "")
            client = self._ensure_repo()

        local_path = kwargs.get("local_path") or client._local_repo_path
        if local_path and Path(local_path).is_dir():
            dt = target_date if isinstance(target_date, date) else date.fromisoformat(str(target_date)[:10])
            local_prs = get_local_prs_for_date(
                local_path, author, dt, registry=self._author_registry
            )
            if local_prs:
                return local_prs  # type: ignore[return-value]

        date_field = kwargs.get("date_field", "created")
        state = kwargs.get("state", "all")
        return client.get_prs(
            author=author, date=target_date, date_field=date_field, state=state
        )

    def fetch_pr_metadata(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Fetch metadata for a pull request.

        Supports:
          fetch_pr_metadata(pr_number)
          fetch_pr_metadata(repo_path, pr_number)
        """
        if len(args) == 2:
            repo_path, pr_num = args
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            client = self._ensure_repo()
        return client._pulls.metadata(int(pr_num))

    def get_pr_commits(self, pr_number: int) -> list[CommitSummary]:
        client = self._ensure_repo()
        return client._pulls.commits(pr_number)

    def get_pr_details(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch full details and files for a pull request.

        Supports:
          get_pr_details(pr_number)
          get_pr_details(owner, repo, pr_number, local_path=None, author="")
        """
        if len(args) >= 3:
            owner, repo, pr_num = args[:3]
            client = self._ensure_repo(owner, repo)
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            client = self._ensure_repo()

        pr_num = int(pr_num)
        local_path = kwargs.get("local_path") or client._local_repo_path
        author = kwargs.get("author", "")

        if local_path and Path(local_path).is_dir():
            local_details = get_local_pr_details(
                local_path, pr_num, author=author, registry=self._author_registry
            )
            if local_details:
                return local_details

        details = client.fetch_pr_metadata(pr_num)
        details["files"] = client._pulls.files(pr_num)
        details["filesTruncated"] = len(details["files"]) < details.get(
            "changedFiles", len(details["files"])
        )
        details["reviews"] = client.get_pr_reviews(pr_num)
        details["comments"] = client._comments(pr_num, details["reviews"])
        return PullRequestItem(details)

    def get_pr_diff(self, pr_number: int) -> DiffResult:
        client = self._ensure_repo()
        return client._pulls.diff(pr_number)

    def fetch_pr_diff(self, *args: Any, **kwargs: Any) -> str:
        """Fetch unified diff text for a PR.

        Supports:
          fetch_pr_diff(pr_number)
          fetch_pr_diff(repo_path, pr_number)
        """
        if len(args) == 2:
            repo_path, pr_num = args
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            client = self._ensure_repo()
        return client.get_pr_diff(int(pr_num)).text

    def save_pr_diff(self, pr_number: int, dest_path: str | Path) -> Path:
        """Explicitly save the PR diff to a designated target file."""
        diff_text = self.fetch_pr_diff(pr_number)
        dest = Path(dest_path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(diff_text, encoding="utf-8")
        return dest

    def get_pr_state(self, *args: Any, **kwargs: Any) -> str | None:
        if len(args) >= 3:
            owner, repo, pr_num = args[:3]
            client = self._ensure_repo(owner, repo)
        elif len(args) == 2 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, pr_num = args[:2]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            client = self._ensure_repo()
        return client._pulls.get_state(int(pr_num))

    def get_all_prs(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """High-throughput listing of PR numbers and authors."""
        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str) and "/" not in args[0]:
            owner, repo = args[:2]
            client = self._ensure_repo(owner, repo)
            state = args[2] if len(args) > 2 else kwargs.get("state", "all")
            limit = args[3] if len(args) > 3 else kwargs.get("limit", 5000)
        elif len(args) >= 1 and isinstance(args[0], str) and "/" in args[0]:
            client = self._ensure_repo(*args[0].split("/", 1))
            state = args[1] if len(args) > 1 else kwargs.get("state", "all")
            limit = args[2] if len(args) > 2 else kwargs.get("limit", 5000)
        else:
            client = self._ensure_repo()
            state = kwargs.get("state", "all")
            limit = kwargs.get("limit", 5000)
        try:
            records = client._runner.run_json(
                "pr",
                "list",
                "--repo",
                client.repo,
                "--state",
                state,
                "--limit",
                str(limit),
                "--json",
                "number,author",
            )
            return records if isinstance(records, list) else []
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Reviews & Discussion
    # -------------------------------------------------------------------------

    def get_pr_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        return [ReviewItem(r) for r in client._reviews.list(pr_number)]

    def get_user_reviews_for_date(
        self, author: str, date: DateInput, *, pr_numbers: Sequence[int] | None = None
    ) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        resolved = client._author(author)
        if resolved is None:
            raise ValueError("author is required")
        reviews = client._reviews.for_user_date(resolved, date, pr_numbers=pr_numbers)
        return [ReviewItem(r) for r in reviews]

    def get_user_reviewed_prs_for_date(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Find pull requests where `author` submitted reviews or merged on `date`.

        Supports:
          get_user_reviewed_prs_for_date(author, date, pr_numbers=None, local_path=None)
          get_user_reviewed_prs_for_date(owner, repo, author, date, local_path=None)
        """
        if len(args) >= 4:
            owner, repo, author, target_date = args[:4]
            client = self._ensure_repo(owner, repo)
        else:
            author = args[0] if args else kwargs.get("author", "")
            target_date = args[1] if len(args) > 1 else kwargs.get("date", "")
            client = self._ensure_repo()

        local_path = kwargs.get("local_path") or client._local_repo_path
        if local_path and Path(local_path).is_dir():
            dt = target_date if isinstance(target_date, date) else date.fromisoformat(str(target_date)[:10])
            local_reviews = get_local_reviewed_prs_for_date(
                local_path, author, dt, registry=self._author_registry
            )
            if local_reviews:
                return local_reviews  # type: ignore[return-value]

        # CLI Search Fallback: reviewed-by:<author> updated:<date>
        iso_str = str(target_date)[:10]
        try:
            search_records = client._runner.run_json(
                "pr",
                "list",
                "--repo",
                client.repo,
                "--state",
                "all",
                "--search",
                f"reviewed-by:{author} updated:{iso_str}",
                "--json",
                "number,title,url",
            )
            if isinstance(search_records, list) and search_records:
                results: list[dict[str, Any]] = []
                for item in search_records:
                    num = item.get("number")
                    if not num:
                        continue
                    # Fetch reviews on this PR to confirm author and date
                    reviews = client.get_pr_reviews(num)
                    matched_review = None
                    for r in reviews:
                        r_user = (r.get("user") or {}).get("login", "")
                        submitted_at = r.get("submitted_at") or r.get("submittedAt", "")
                        if self.is_author_match(author, login=r_user) and submitted_at.startswith(iso_str):
                            matched_review = r
                            break
                    results.append(
                        ReviewItem(
                            {
                                "pr_number": num,
                                "pr_title": item.get("title", ""),
                                "reviewer": author,
                                "state": matched_review.get("state", "REVIEWED") if matched_review else "REVIEWED",
                                "submitted_at": matched_review.get("submitted_at", iso_str) if matched_review else iso_str,
                                "url": item.get("url", ""),
                            }
                        )
                    )
                if results:
                    return results
        except Exception:
            pass

        return client.get_user_reviews_for_date(author, target_date)

    def _comments(
        self, pr_number: int, reviews: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        return [
            *({**item, "kind": "issue"} for item in client._issues.comments(pr_number)),
            *(
                {**item, "kind": "inline"}
                for item in client._reviews.inline_comments(pr_number)
            ),
            *({**item, "kind": "review"} for item in reviews if item.get("body")),
        ]

    def fetch_pr_comments(
        self,
        pr_number: int,
        *,
        date: DateInput | None = None,
        author: str | None = None,
    ) -> list[dict[str, Any]]:
        client = self._ensure_repo()
        author = client._author(author)
        window = DateWindow.for_date(date, client._timezone) if date is not None else None
        comments = client._comments(pr_number, client.get_pr_reviews(pr_number))
        selected = []
        for item in comments:
            timestamp = (
                item.get("submitted_at")
                if item["kind"] == "review"
                else item.get("created_at")
            )
            if window and not window.contains(timestamp):
                continue
            login = (item.get("user") or {}).get("login") or ""
            if author is not None and login.casefold() != author.casefold():
                continue
            selected.append(item)
        return sorted(
            selected,
            key=lambda item: (
                parse_timestamp(
                    item.get("submitted_at")
                    or item.get("created_at")
                    or "1970-01-01T00:00:00Z"
                ),
                item.get("id", 0),
                item["kind"],
            ),
        )

    def get_pr_user_comments(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> list[str]:
        """Fetch discussion and review comments posted by author on a PR with local disk caching.

        Supports:
          get_pr_user_comments(pr_number, author, date=None, use_cache=True, cache_path=...)
          get_pr_user_comments(owner, repo, pr_number, author, date=None, local_path=..., use_cache=True, cache_path=...)
        """
        if len(args) >= 4:
            owner, repo, pr_num, author = args[:4]
            client = self._ensure_repo(owner, repo)
            target_date = args[4] if len(args) > 4 else kwargs.get("date")
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            author = args[1] if len(args) > 1 else kwargs.get("author")
            target_date = kwargs.get("date")
            client = self._ensure_repo()

        owner = client._api.repository.owner
        repo = client._api.repository.name
        use_cache = kwargs.get("use_cache", True)
        cache_path = kwargs.get("cache_path", ".cache/pr_comments.json")
        date_str = str(target_date)[:10] if target_date else None

        return fetch_pr_user_comments(
            client,
            owner,
            repo,
            int(pr_num),
            author,
            target_date=date_str,
            use_cache=use_cache,
            cache_path=cache_path,
        )

    # -------------------------------------------------------------------------
    # Branch Checkout & Commenting
    # -------------------------------------------------------------------------

    def checkout_pr_branch(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Check out a pull request branch locally.

        Supports:
          checkout_pr_branch(pr_number, local_repo_path=None)
          checkout_pr_branch(repo_path, pr_number, local_repo_path=None)
        """
        if len(args) >= 2 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, pr_num = args[:2]
            client = self._ensure_repo(*repo_path.split("/", 1))
            local_path = args[2] if len(args) > 2 else kwargs.get("local_repo_path")
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            client = self._ensure_repo()
            local_path = kwargs.get("local_repo_path") or client._local_repo_path

        path = local_path if local_path is not None else client._local_repo_path
        if path is None:
            raise ValueError("local_repo_path is required for checkout")
        return client._pulls.checkout(int(pr_num), path)

    def post_pr_comment(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Post a comment to a pull request.

        Supports:
          post_pr_comment(pr_number, body)
          post_pr_comment(repo_path, pr_number, body_or_filepath)
        """
        if len(args) >= 3 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, pr_num, body_arg = args[:3]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            body_arg = args[1] if len(args) > 1 else kwargs.get("body")
            client = self._ensure_repo()

        body = str(body_arg)
        if Path(body).is_file():
            try:
                body = Path(body).read_text(encoding="utf-8")
            except OSError:
                pass

        return client._issues.post_pr_comment(int(pr_num), body)

    def create_pull_request_review(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create and submit a pull request review.

        Supports:
          create_pull_request_review(pr_number, commit_id, comments, body="", event="COMMENT")
          create_pull_request_review(repo_path, pr_number, commit_id, comments, body="", event="COMMENT")
        """
        if len(args) >= 4 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, pr_num, commit_id, comments = args[:4]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            pr_num = args[0] if args else kwargs.get("pr_number")
            commit_id = args[1] if len(args) > 1 else kwargs.get("commit_id")
            comments = args[2] if len(args) > 2 else kwargs.get("comments")
            client = self._ensure_repo()

        body = kwargs.get("body", "")
        event = kwargs.get("event", "COMMENT")
        return client._reviews.create(int(pr_num), commit_id, comments, body=body, event=event)

    # -------------------------------------------------------------------------
    # Auditing & Bulk Mining
    # -------------------------------------------------------------------------

    def scan_foreign_prs_for_author(
        self,
        target_author: str,
        pr_numbers: Sequence[int],
        invalid_labels: Sequence[str] = ("invalid", "spam", "wontfix"),
    ) -> list[int]:
        client = self._ensure_repo()
        matching_prs = []
        for num in pr_numbers:
            _, is_match, _ = scan_foreign_pr(
                client._runner,
                client.repo,
                num,
                target_author,
                registry=self._author_registry,
                invalid_labels=invalid_labels,
            )
            if is_match:
                matching_prs.append(num)
        return matching_prs

    def scan_contributor_contributions(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[list[int], list[str]]:
        if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], str) and "/" not in args[0]:
            owner, repo, author = args[:3]
            client = self._ensure_repo(owner, repo)
        elif len(args) >= 2 and isinstance(args[0], str) and "/" in args[0]:
            repo_path, author = args[:2]
            client = self._ensure_repo(*repo_path.split("/", 1))
        else:
            author = args[0] if args else kwargs.get("target_author", "")
            client = self._ensure_repo()

        limit = kwargs.get("limit", 5000)
        include_foreign = kwargs.get("include_foreign", True)
        invalid_labels = kwargs.get("invalid_labels", ("invalid", "spam", "wontfix"))
        max_workers = kwargs.get("max_workers", 10)
        return scan_contributor_contributions(
            client._runner,
            client.repo,
            author,
            limit=limit,
            include_foreign=include_foreign,
            invalid_labels=invalid_labels,
            max_workers=max_workers,
            registry=self._author_registry,
        )

    # -------------------------------------------------------------------------
    # Multi-Project Configuration
    # -------------------------------------------------------------------------

    @staticmethod
    def load_projects(projects_file: str | Path = "projects.json") -> list[ProjectConfig]:
        """Load projects configuration from a JSON file."""
        path = Path(projects_file)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [ProjectConfig.from_dict(item) for item in data if isinstance(item, dict)]
        except Exception:
            pass
        return []
