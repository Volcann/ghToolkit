from __future__ import annotations

import sys

from .audit import (
    ProgressQueue,
    get_pr_state,
    scan_contributor_contributions,
    scan_foreign_pr,
)
from .client import (
    GitHubClient,
    checkout_pr_branch,
    create_pull_request_review,
    fetch_pr_diff,
    fetch_pr_metadata,
    load_projects,
    post_pr_comment,
)

# Backward-compatibility submodule mapping for legacy direct imports
from .client import client as _github_client_module
from .commit import CommitService, CommitSummary
from .core import (
    AuthorRegistry,
    DateInput,
    DateWindow,
    DiffStorageError,
    GhCommandError,
    GhExecutionError,
    GhNotInstalledError,
    GhResponseError,
    GhRunner,
    GhTimeoutError,
    GitHubError,
    api,
    dates,
    errors,
    git_local,
    identity,
    is_author_match,
    parse_date,
    parse_timestamp,
    register_author_alias,
    resolve_timezone,
    run_gh,
    run_git_command,
    runner,
    validation,
)
from .issues import IssueService
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
from .pull_request import PullRequestService, ReviewService
from .storage import (
    CommentCache,
    DiffResult,
    DiffStore,
    comments,
    diffs,
    fetch_pr_user_comments,
)
from .utils import (
    clean_commit_message,
    create_pr_review,
    format_iso_date,
    is_merge_commit,
    run_gh_json,
    run_git,
)

github_client = _github_client_module
sys.modules.setdefault("ghtoolkit.github_client", _github_client_module)
sys.modules.setdefault("ghtoolkit.api", api)
sys.modules.setdefault("ghtoolkit.dates", dates)
sys.modules.setdefault("ghtoolkit.errors", errors)
sys.modules.setdefault("ghtoolkit.git_local", git_local)
sys.modules.setdefault("ghtoolkit.identity", identity)
sys.modules.setdefault("ghtoolkit.runner", runner)
sys.modules.setdefault("ghtoolkit.validation", validation)
sys.modules.setdefault("ghtoolkit.diff_store", diffs)
sys.modules.setdefault("ghtoolkit.comments", comments)

__all__ = [
    "AuthorRegistry",
    "CommentCache",
    "CommitInfo",
    "CommitItem",
    "CommitService",
    "CommitSummary",
    "DateInput",
    "DateWindow",
    "DiffResult",
    "DiffStorageError",
    "DiffStore",
    "GhCommandError",
    "GhExecutionError",
    "GhNotInstalledError",
    "GhResponseError",
    "GhRunner",
    "GhTimeoutError",
    "GitHubClient",
    "GitHubError",
    "InlineReviewComment",
    "IssueService",
    "ProgressQueue",
    "ProjectConfig",
    "PullRequestInfo",
    "PullRequestItem",
    "PullRequestService",
    "ReviewInfo",
    "ReviewItem",
    "ReviewService",
    "checkout_pr_branch",
    "clean_commit_message",
    "create_pr_review",
    "create_pull_request_review",
    "fetch_pr_diff",
    "fetch_pr_metadata",
    "fetch_pr_user_comments",
    "format_iso_date",
    "get_pr_state",
    "is_author_match",
    "is_merge_commit",
    "load_projects",
    "parse_date",
    "parse_timestamp",
    "post_pr_comment",
    "register_author_alias",
    "resolve_timezone",
    "run_gh",
    "run_gh_json",
    "run_git",
    "run_git_command",
    "scan_contributor_contributions",
    "scan_foreign_pr",
]
