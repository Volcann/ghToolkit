from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..core.identity import is_author_match


class CommentCache:
    """Manages disk-backed JSON cache for PR comments to reduce GitHub API calls."""

    def __init__(self, cache_path: str | Path = ".cache/pr_comments.json"):
        self.cache_path = Path(cache_path)

    def load(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cache_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.cache_path)
        except OSError:
            pass

    def get_comments(
        self, repo_key: str, pr_number: int
    ) -> list[dict[str, Any]] | None:
        data = self.load()
        return data.get(repo_key, {}).get(str(pr_number))

    def set_comments(
        self, repo_key: str, pr_number: int, comments: list[dict[str, Any]]
    ) -> None:
        data = self.load()
        repo_data = data.setdefault(repo_key, {})
        repo_data[str(pr_number)] = comments
        self.save(data)


def fetch_pr_user_comments(
    api_or_client: Any,
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    author: str,
    target_date: str | None = None,
    use_cache: bool = True,
    cache_path: str | Path = ".cache/pr_comments.json",
) -> list[str]:
    """Fetch all discussion and review comments posted by author on a PR.

    Checks:
    1. Local comments cache file (.cache/pr_comments.json).
    2. GitHub CLI / API for issue comments, inline review comments, and review bodies.
    """
    repo_key = f"{repo_owner}/{repo_name}"
    cache = CommentCache(cache_path)
    comments_found: list[str] = []

    if use_cache:
        cached_entries = cache.get_comments(repo_key, pr_number)
        if cached_entries:
            for item in cached_entries:
                c_auth = item.get("author", "")
                c_date = item.get("created_at", "")
                c_body = item.get("body", "").strip()
                if is_author_match(author, login=c_auth):  # noqa: SIM102
                    if not target_date or c_date.startswith(target_date):  # noqa: SIM102
                        if c_body and c_body not in comments_found:
                            comments_found.append(c_body)
            if comments_found:
                return comments_found

    # Query API endpoints for comments
    endpoints = [
        f"repos/{repo_key}/issues/{pr_number}/comments",
        f"repos/{repo_key}/pulls/{pr_number}/comments",
        f"repos/{repo_key}/pulls/{pr_number}/reviews",
    ]

    new_cache_entries: list[dict[str, Any]] = []
    for endpoint in endpoints:
        try:
            raw_data = None
            if hasattr(api_or_client, "_rest_get") and (
                not getattr(api_or_client, "prefer_cli", True)
                or not getattr(api_or_client, "has_gh_cli", True)
            ):
                raw_data = api_or_client._rest_get(endpoint)
            elif hasattr(api_or_client, "_api") and hasattr(api_or_client._api, "list"):
                raw_data = api_or_client._api.list(
                    endpoint.replace(f"repos/{repo_key}/", "")
                )
            elif hasattr(api_or_client, "list"):
                raw_data = api_or_client.list(
                    endpoint.replace(f"repos/{repo_key}/", "")
                )
            elif hasattr(api_or_client, "run_json"):
                raw_data = api_or_client.run_json("api", endpoint)
            elif hasattr(api_or_client, "_run_gh_command"):
                raw_data = api_or_client._run_gh_command(["api", endpoint])
            elif hasattr(api_or_client, "_rest_get"):
                raw_data = api_or_client._rest_get(endpoint)
        except Exception:  # noqa: BLE001
            raw_data = None

        if isinstance(raw_data, list):
            for item in raw_data:
                if not isinstance(item, dict):
                    continue
                user_login = item.get("user", {}).get("login", "")
                c_date = (
                    item.get("created_at")
                    or item.get("submitted_at")
                    or item.get("updated_at")
                    or ""
                )
                c_body = item.get("body", "").strip()
                if not c_body:
                    continue

                new_cache_entries.append(
                    {
                        "id": item.get("id"),
                        "author": user_login,
                        "created_at": c_date,
                        "body": c_body,
                    }
                )

                if is_author_match(author, login=user_login):  # noqa: SIM102
                    if not target_date or c_date.startswith(target_date):  # noqa: SIM102
                        if c_body and c_body not in comments_found:
                            comments_found.append(c_body)

    if not comments_found and new_cache_entries:
        for item in new_cache_entries:
            if is_author_match(author, login=item["author"]):  # noqa: SIM102
                if item["body"] not in comments_found:
                    comments_found.append(item["body"])

    if use_cache and new_cache_entries:
        cache.set_comments(repo_key, pr_number, new_cache_entries)

    return comments_found
