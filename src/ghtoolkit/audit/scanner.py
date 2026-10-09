from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

_log = logging.getLogger(__name__)
_LOG_FILE = Path(__file__).parent / "audit.log"

_file_handler = logging.FileHandler(_LOG_FILE)
_file_handler.setLevel(logging.ERROR)
_log.addHandler(_file_handler)


def _is_match(
    target: str,
    name: str = "",
    email: str = "",
    login: str = "",
) -> bool:
    t = target.strip().lower()
    if not t:
        return False
    for candidate in (name.strip().lower(), email.strip().lower(), login.strip().lower()):
        if candidate and (t == candidate or t in candidate or candidate in t):
            return True
    return False


class ProgressQueue:
    """Manages a file-backed, resumable queue for repository auditing and progress checkpoints."""

    def __init__(self, filepath: str | Path = "progress.txt"):
        self.filepath = Path(filepath)

    def load(self) -> list[str]:
        if not self.filepath.exists():
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    def save(self, items: Sequence[str]) -> None:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.filepath.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(f"{item}\n")
            os.replace(tmp, self.filepath)
        except OSError:
            pass

    def pop(self) -> str | None:
        items = self.load()
        if not items:
            return None
        head = items.pop(0)
        self.save(items)
        return head

    def push(self, item: str) -> None:
        items = self.load()
        items.append(item)
        self.save(items)

    def is_empty(self) -> bool:
        return len(self.load()) == 0

    def count(self) -> int:
        return len(self.load())

    @staticmethod
    def make_pr_item(owner: str, repo: str, pr_num: int) -> str:
        return f"{owner}/{repo}:PR:{pr_num}"

    @staticmethod
    def make_commit_item(owner: str, repo: str, sha: str) -> str:
        return f"{owner}/{repo}:Commit:{sha}"

    @staticmethod
    def parse_item(item_str: str) -> tuple[str, str, str, str]:
        """Parse item string into (owner, repo, kind, identifier)."""
        if ":" not in item_str:
            return ("", "", "UNKNOWN", item_str)
        parts = item_str.split(":", 2)
        if len(parts) == 3:
            project_key, kind, identifier = parts
            if "/" in project_key:
                owner, repo = project_key.split("/", 1)
            else:
                owner, repo = "", project_key
            return (owner, repo, kind, identifier)
        elif len(parts) == 2:
            kind, identifier = parts
            return ("", "", kind, identifier)
        return ("", "", "UNKNOWN", item_str)


def get_pr_state(runner: Any, repo_cli: str, pr_number: int) -> str | None:
    """Retrieve current state ('OPEN', 'MERGED', 'CLOSED') of a pull request."""
    try:
        data = runner.run_json(
            "pr", "view", str(pr_number), "--repo", repo_cli, "--json", "state"
        )
        if isinstance(data, dict):
            return data.get("state")
    except Exception:
        pass
    return None


def scan_foreign_pr(
    runner: Any,
    repo_cli: str,
    pr_number: int,
    target_author: str,
    registry: Any | None = None,
    invalid_labels: Sequence[str] = ("invalid", "spam", "wontfix"),
) -> tuple[int, bool, list[str]]:
    """Inspect a foreign PR to verify if it contains native commits authored by `target_author`."""
    matcher = registry.is_match if registry else _is_match
    invalid_set = {lbl.lower() for lbl in invalid_labels}

    try:
        data = runner.run_json(
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo_cli,
            "--json",
            "commits,labels",
        )
    except Exception:
        _log.exception("scan error for PR %s", pr_number)
        return pr_number, False, []

    if not isinstance(data, dict):
        return pr_number, False, []

    labels = data.get("labels", [])
    for label in labels:
        lbl_name = (
            label.get("name", "").lower()
            if isinstance(label, dict)
            else str(label).lower()
        )
        if lbl_name in invalid_set:
            return pr_number, False, []

    valid_commit_messages: list[str] = []
    commits = data.get("commits", [])

    for commit in commits:
        if not isinstance(commit, dict):
            continue
        authors = commit.get("authors", [])
        if not authors:
            continue

        c_auth = authors[0] if isinstance(authors, list) and authors else {}
        git_name = c_auth.get("name", "")
        github_login = c_auth.get("login", "")

        if matcher(target_author, name=git_name, login=github_login):
            message = commit.get("messageHeadline") or commit.get("message", "")
            if not message:
                continue
            message_lower = message.lower()
            if "merge" in message_lower or f"#{pr_number}" in message:
                continue
            valid_commit_messages.append(message)

    has_valid = len(valid_commit_messages) > 0
    return pr_number, has_valid, valid_commit_messages


def scan_contributor_contributions(
    runner: Any,
    repo_cli: str,
    target_author: str,
    limit: int = 5000,
    include_foreign: bool = True,
    invalid_labels: Sequence[str] = ("invalid", "spam", "wontfix"),
    max_workers: int = 10,
    registry: Any | None = None,
) -> tuple[list[int], list[str]]:
    """Scan all pull requests in a repository for contributions by `target_author`."""
    matcher = registry.is_match if registry else _is_match

    try:
        all_prs_data = runner.run_json(
            "pr",
            "list",
            "--repo",
            repo_cli,
            "--state",
            "all",
            "--limit",
            str(limit),
            "--json",
            "number,author",
        )
    except Exception:
        _log.exception("scan error for PRs list")
        all_prs_data = []

    if not isinstance(all_prs_data, list):
        return [], []

    final_prs: list[int] = []
    all_commits: list[str] = []
    foreign_prs_to_scan: list[int] = []

    for pr in all_prs_data:
        if not isinstance(pr, dict):
            continue
        pr_num = pr.get("number")
        if not pr_num:
            continue

        pr_author = ""
        auth_obj = pr.get("author")
        if isinstance(auth_obj, dict):
            pr_author = auth_obj.get("login", "")
        elif isinstance(auth_obj, str):
            pr_author = auth_obj

        if pr_author and matcher(target_author, login=pr_author):
            final_prs.append(pr_num)
        elif include_foreign:
            foreign_prs_to_scan.append(pr_num)

    if include_foreign and foreign_prs_to_scan:
        workers = min(max_workers, len(foreign_prs_to_scan), 20)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    scan_foreign_pr,
                    runner,
                    repo_cli,
                    num,
                    target_author,
                    registry,
                    invalid_labels,
                )
                for num in foreign_prs_to_scan
            ]
            for future in as_completed(futures):
                pr_num, is_match, messages = future.result()
                if is_match:
                    final_prs.append(pr_num)
                    all_commits.extend(messages)

    final_prs.sort()
    return final_prs, all_commits
