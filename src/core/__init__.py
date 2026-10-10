"""Core utilities for runner, API, dates, validation, errors, git, and identity."""

from .api import GhAPI, Repository
from .dates import DateInput, DateWindow, parse_date, parse_timestamp, resolve_timezone
from .errors import (
    DiffStorageError,
    GhCommandError,
    GhExecutionError,
    GhNotInstalledError,
    GhResponseError,
    GhTimeoutError,
    GitHubError,
)
from .git_local import (
    get_local_commit_branch,
    get_local_commit_pull_requests,
    get_local_commits_for_date,
    get_local_pr_details,
    get_local_prs_for_date,
    get_local_reviewed_prs_for_date,
    is_merge_commit_message,
    run_git_command,
)
from .identity import AuthorRegistry, is_author_match, register_author_alias
from .runner import GhRunner, run_gh
from .validation import (
    nonempty,
    object_list,
    object_value,
    positive_number,
    result_limit,
)

__all__ = [
    "GhAPI",
    "Repository",
    "DateInput",
    "DateWindow",
    "parse_date",
    "parse_timestamp",
    "resolve_timezone",
    "GitHubError",
    "GhNotInstalledError",
    "GhExecutionError",
    "GhTimeoutError",
    "GhCommandError",
    "GhResponseError",
    "DiffStorageError",
    "run_git_command",
    "get_local_commits_for_date",
    "get_local_prs_for_date",
    "get_local_pr_details",
    "get_local_reviewed_prs_for_date",
    "get_local_commit_pull_requests",
    "get_local_commit_branch",
    "is_merge_commit_message",
    "AuthorRegistry",
    "is_author_match",
    "register_author_alias",
    "GhRunner",
    "run_gh",
    "nonempty",
    "positive_number",
    "result_limit",
    "object_value",
    "object_list",
]
