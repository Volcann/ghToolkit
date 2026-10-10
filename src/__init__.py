from __future__ import annotations

import sys

from .audit import (
    ProgressQueue,
    get_pr_state,
    scan_contributor_contributions,
    scan_foreign_pr,
)
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
from .client import (
    GitHubClient,
    checkout_pr_branch,
    create_pull_request_review,
    fetch_pr_diff,
    fetch_pr_metadata,
    load_projects,
    post_pr_comment,
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

# Backward-compatibility submodule mapping for legacy direct imports
from .client import client as _github_client_module

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
    "GitHubClient",
    "load_projects",
    "fetch_pr_metadata",
    "fetch_pr_diff",
    "checkout_pr_branch",
    "post_pr_comment",
    "create_pull_request_review",
    "create_pr_review",
    "CommitService",
    "CommitSummary",
    "PullRequestService",
    "ReviewService",
    "IssueService",
    "GhRunner",
    "run_gh",
    "run_gh_json",
    "run_git",
    "DiffResult",
    "DiffStore",
    "InlineReviewComment",
    "CommitInfo",
    "CommitItem",
    "PullRequestInfo",
    "PullRequestItem",
    "ReviewInfo",
    "ReviewItem",
    "ProjectConfig",
    "AuthorRegistry",
    "is_author_match",
    "register_author_alias",
    "CommentCache",
    "fetch_pr_user_comments",
    "ProgressQueue",
    "get_pr_state",
    "scan_foreign_pr",
    "scan_contributor_contributions",
    "run_git_command",
    "GitHubError",
    "GhNotInstalledError",
    "GhExecutionError",
    "GhTimeoutError",
    "GhCommandError",
    "GhResponseError",
    "DiffStorageError",
    "DateInput",
    "DateWindow",
    "parse_date",
    "parse_timestamp",
    "resolve_timezone",
    "clean_commit_message",
    "format_iso_date",
    "is_merge_commit",
]
