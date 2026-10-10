from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


def run_gh(
    args: list[str], cwd: str | Path | None = None
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603
            ["gh", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip(), file=sys.stderr)
        return None
    except FileNotFoundError:
        print("gh CLI not found — install and authenticate it first.", file=sys.stderr)
        return None


def run_gh_json(args: list[str], cwd: str | Path | None = None) -> Any:
    result = run_gh(args, cwd=cwd)
    if result is None:
        return None
    return json.loads(result.stdout)


def fetch_pr_metadata(repo: str, pr_number: int) -> dict[str, Any] | None:
    return run_gh_json(
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "number,title,author,state,url,createdAt,commits",
        ]
    )


def fetch_pr_diff(repo: str, pr_number: int) -> str:
    result = run_gh(["pr", "diff", str(pr_number), "--repo", repo, "--color", "never"])
    return result.stdout if result else ""


def checkout_pr_branch(repo: str, pr_number: int, local_path: str | Path) -> bool:
    result = run_gh(["pr", "checkout", str(pr_number), "--repo", repo], cwd=local_path)
    return result is not None


def post_pr_comment(repo: str, pr_number: int, comment_file: str | Path) -> bool:
    result = run_gh(
        [
            "pr",
            "comment",
            str(pr_number),
            "--repo",
            repo,
            "--body-file",
            str(comment_file),
        ]
    )
    return result is not None


def create_pr_review(
    repo: str,
    pr_number: int,
    commit_sha: str,
    comments: list[dict[str, Any]],
    body: str = "",
    event: str = "COMMENT",
) -> bool:
    owner, name = repo.split("/", 1)
    payload = json.dumps(
        {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
            "comments": comments,
        }
    )
    result = subprocess.run(  # noqa: S603, PLW1510
        [  # noqa: S607
            "gh",
            "api",
            f"/repos/{owner}/{name}/pulls/{pr_number}/reviews",
            "--method",
            "POST",
            "--input",
            "-",
            "--header",
            "Accept: application/vnd.github+json",
        ],
        input=payload,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def run_git(args: list[str], cwd: str | Path) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        return result.stdout  # noqa: TRY300
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def format_iso_date(dt: date) -> str:
    return dt.strftime("%Y-%m-%d")


def clean_commit_message(msg: str) -> str:
    if not msg:
        return ""
    lines = [line.strip() for line in msg.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def is_merge_commit(msg: str) -> bool:
    lower = msg.lower()
    return (
        lower.startswith("merge pull request")  # noqa: PIE810
        or lower.startswith("merge branch")
        or "merge remote-tracking branch" in lower
    )
