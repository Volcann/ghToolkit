from __future__ import annotations

import os
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .identity import AuthorRegistry, is_author_match
from .models import CommitItem, PullRequestItem, ReviewItem


def run_git_command(
    args: list[str], cwd: str | Path, timeout: float = 30.0
) -> str | None:
    """Run a git command in a local directory, returning stdout or None on failure."""
    if not cwd:
        return None
    try:
        dir_path = Path(cwd).expanduser().resolve()
        if not dir_path.is_dir():
            return None
    except OSError:
        return None

    cmd = ["git", "-C", str(dir_path), *args]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        return res.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def is_merge_commit_message(message: str) -> bool:
    """Check if a commit headline is a git merge commit."""
    first_line = message.strip().splitlines()[0] if message else ""
    return (
        first_line.startswith("Merge ")
        or "Merge branch " in first_line
        or "Merge pull request #" in first_line
    )


def get_local_commits_for_date(
    local_path: str | Path,
    author: str,
    target_date: date,
    registry: AuthorRegistry | None = None,
) -> list[CommitItem]:
    """Retrieve commits authored by `author` on `target_date` using local git repository logs."""
    iso_date = target_date.isoformat()
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    git_out = run_git_command(
        [
            "log",
            f"--since={prev_date.isoformat()}T12:00:00",
            f"--until={next_date.isoformat()}T12:00:00",
            "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
            "--all",
        ],
        cwd=local_path,
    )
    if not git_out:
        return []

    matcher = registry.is_match if registry else is_author_match
    results: list[CommitItem] = []

    for record in git_out.strip().split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) >= 6:
            h, s, b, an, ae, dt = parts[:6]
            dt_clean = dt.strip()
            if is_merge_commit_message(s):
                continue
            if not matcher(author, name=an, email=ae):
                continue

            # Verify target_date in local timezone or UTC
            try:
                commit_dt = datetime.fromisoformat(dt_clean)
                if (
                    commit_dt.date() != target_date
                    and commit_dt.astimezone(timezone.utc).date() != target_date
                ):
                    continue
            except Exception:
                if not dt_clean.startswith(iso_date):
                    continue

            # Extract branch
            branch_name = None
            branch_out = run_git_command(["branch", "--contains", h], cwd=local_path)
            if branch_out:
                branches = [
                    line.strip().lstrip("* ")
                    for line in branch_out.strip().splitlines()
                    if line.strip() and not line.strip().startswith("(")
                ]
                if branches:
                    branch_name = branches[0]

            # Extract changed files
            commit_files: list[str] = []
            files_out = run_git_command(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", h],
                cwd=local_path,
            )
            if files_out:
                commit_files = [f.strip() for f in files_out.splitlines() if f.strip()]

            msg = f"{s}\n\n{b}".strip() if b.strip() else s
            results.append(
                CommitItem(
                    {
                        "sha": h,
                        "hash": h,
                        "message": msg,
                        "author_name": an,
                        "author_login": author,
                        "author_email": ae,
                        "date": dt_clean,
                        "branch": branch_name,
                        "files": commit_files,
                    }
                )
            )

    return results


def get_local_prs_for_date(
    local_path: str | Path,
    author: str,
    target_date: date,
    registry: AuthorRegistry | None = None,
) -> list[PullRequestItem]:
    """Retrieve pull requests merged or created on `target_date` using local git logs."""
    iso_date = target_date.isoformat()
    merge_out = run_git_command(
        [
            "log",
            f"--since={iso_date}T00:00:00",
            f"--until={iso_date}T23:59:59",
            "--grep=Merge pull request #",
            "--format=%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
            "--all",
        ],
        cwd=local_path,
    )
    if not merge_out:
        return []

    matcher = registry.is_match if registry else is_author_match
    local_prs: list[PullRequestItem] = []

    for line in merge_out.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x1f")
        if len(parts) >= 6:
            h, s, b, an, ae, dt = parts[:6]
            match = re.search(r"Merge pull request #(\d+) from (.+)", s)
            if not match:
                continue
            pr_num = int(match.group(1))
            branch_raw = match.group(2).strip()

            # Commits in this merged PR
            commits_list: list[CommitItem] = []
            pr_commits_out = run_git_command(
                [
                    "log",
                    f"{h}^1..{h}^2",
                    "--format=%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
                ],
                cwd=local_path,
            )
            primary_title = b.strip().splitlines()[0] if b.strip() else ""

            pr_has_author_commits = False
            if pr_commits_out:
                for c_line in pr_commits_out.strip().split("\n"):
                    if not c_line:
                        continue
                    c_parts = c_line.split("\x1f")
                    if len(c_parts) >= 6:
                        ch, cs, cb, can, cae, cdt = c_parts[:6]
                        if is_merge_commit_message(cs):
                            continue
                        if not primary_title:
                            primary_title = cs
                        is_match = matcher(author, name=can, email=cae)
                        if is_match:
                            pr_has_author_commits = True
                        commits_list.append(
                            CommitItem(
                                {
                                    "sha": ch,
                                    "hash": ch,
                                    "message": f"{cs}\n\n{cb}".strip(),
                                    "author_name": can,
                                    "author_login": author if is_match else can,
                                    "date": cdt,
                                    "pr_number": pr_num,
                                }
                            )
                        )

            if not primary_title:
                primary_title = branch_raw

            if pr_has_author_commits or matcher(author, name=an, email=ae):
                local_prs.append(
                    PullRequestItem(
                        {
                            "number": pr_num,
                            "title": primary_title,
                            "body": b.strip(),
                            "author_login": author,
                            "state": "MERGED",
                            "created_at": dt,
                            "head_ref": branch_raw,
                            "headRefName": branch_raw,
                            "is_own": True,
                            "commits": commits_list,
                        }
                    )
                )

    return local_prs


def get_local_pr_details(
    local_path: str | Path,
    pr_number: int,
    author: str = "",
    registry: AuthorRegistry | None = None,
) -> PullRequestItem | None:
    """Retrieve pull request details from local merge commit if present."""
    git_out = run_git_command(
        [
            "log",
            f"--grep=Merge pull request #{pr_number} ",
            "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
            "-n",
            "1",
        ],
        cwd=local_path,
    )
    if not git_out or not git_out.strip():
        return None

    parts = git_out.strip().lstrip("\x1e").split("\x1f")
    if len(parts) < 6:
        return None
    h, s, b, an, ae, dt = parts[:6]

    # Commits inside PR
    commits_list: list[CommitItem] = []
    pr_commits_out = run_git_command(
        ["log", f"{h}^1..{h}^2", "--format=%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI"],
        cwd=local_path,
    )
    if pr_commits_out:
        for c_line in pr_commits_out.strip().split("\n"):
            if not c_line:
                continue
            c_parts = c_line.split("\x1f")
            if len(c_parts) >= 6:
                ch, cs, cb, can, cae, cdt = c_parts[:6]
                c_files_out = run_git_command(
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", ch],
                    cwd=local_path,
                )
                c_files = [f.strip() for f in c_files_out.splitlines()] if c_files_out else []
                commits_list.append(
                    CommitItem(
                        {
                            "sha": ch,
                            "hash": ch,
                            "message": f"{cs}\n\n{cb}".strip(),
                            "author_name": can,
                            "author_login": can,
                            "date": cdt,
                            "pr_number": pr_number,
                            "files": c_files,
                        }
                    )
                )

    primary_title = b.strip().splitlines()[0] if b.strip() else ""
    if not primary_title and commits_list:
        primary_title = commits_list[0].headline
    if not primary_title:
        primary_title = s

    m_branch = re.search(r"Merge pull request #\d+ from (.+)", s)
    head_ref = m_branch.group(1).strip() if m_branch else ""

    # Changed files
    pr_files_out = run_git_command(
        ["diff", "--name-only", f"{h}^1...{h}^2"],
        cwd=local_path,
    )
    pr_files = [f.strip() for f in pr_files_out.splitlines() if f.strip()] if pr_files_out else []

    matcher = registry.is_match if registry else is_author_match
    is_own = matcher(author, name=an, email=ae) if author else True

    return PullRequestItem(
        {
            "number": pr_number,
            "title": primary_title,
            "body": b.strip(),
            "author_login": author if is_own and author else an,
            "state": "MERGED",
            "created_at": dt,
            "head_ref": head_ref,
            "headRefName": head_ref,
            "is_own": is_own,
            "commits": commits_list,
            "files": pr_files,
            "files_changed": pr_files,
        }
    )


def get_local_commit_pull_requests(
    local_path: str | Path,
    commit_sha: str,
) -> list[dict[str, Any]]:
    """Determine pull requests associated with a commit via local git merge ancestry or message."""
    ancestry_out = ""
    for ref in ["origin/dev", "dev", "origin/main", "main", "HEAD"]:
        out = run_git_command(
            [
                "log",
                "--merges",
                "--ancestry-path",
                f"{commit_sha}..{ref}",
                "--oneline",
            ],
            cwd=local_path,
        )
        if out and out.strip():
            ancestry_out = out.strip()
            break

    if ancestry_out:
        pr_matches = [
            line for line in ancestry_out.splitlines() if "Merge pull request #" in line
        ]
        if pr_matches:
            earliest_pr = pr_matches[-1]
            m = re.search(r"Merge pull request #(\d+)", earliest_pr)
            if m:
                return [{"number": int(m.group(1))}]

    # Check commit message for #<number>
    c_msg = run_git_command(["log", "-n", "1", "--format=%s", commit_sha], cwd=local_path)
    if c_msg:
        m_num = re.search(r"#(\d+)", c_msg)
        if m_num:
            return [{"number": int(m_num.group(1))}]

    return []


def get_local_commit_branch(
    local_path: str | Path,
    commit_sha: str,
    commit_message: str = "",
) -> str:
    """Find the most relevant feature branch name for a commit SHA."""
    branch_out = run_git_command(
        ["branch", "-a", "--contains", commit_sha], cwd=local_path
    )
    if branch_out:
        raw_branches = [
            b.strip().lstrip("* ").replace("remotes/origin/", "")
            for b in branch_out.strip().splitlines()
            if b.strip() and "HEAD" not in b and not b.strip().startswith("(")
        ]
        feature_branches = [
            b
            for b in raw_branches
            if b not in ("dev", "stage", "main", "master", "origin/dev", "origin/stage")
        ]
        ticket_m = re.search(r"([A-Za-z]{2,}-\d+)", commit_message)
        if ticket_m:
            t = ticket_m.group(1).lower()
            for b in feature_branches:
                if t in b.lower():
                    return b
        if feature_branches:
            return feature_branches[0]
        if raw_branches:
            return raw_branches[0]
    return "main"


def get_local_reviewed_prs_for_date(
    local_path: str | Path,
    author: str,
    target_date: date,
    registry: AuthorRegistry | None = None,
) -> list[ReviewItem]:
    """Find PRs where `author` merged or reviewed on `target_date` using local git logs."""
    iso_date = target_date.isoformat()
    merge_out = run_git_command(
        [
            "log",
            f"--since={iso_date}T00:00:00",
            f"--until={iso_date}T23:59:59",
            "--merges",
            "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
            "--all",
        ],
        cwd=local_path,
    )
    if not merge_out:
        return []

    matcher = registry.is_match if registry else is_author_match
    local_reviews: list[ReviewItem] = []

    for record in merge_out.strip().split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) >= 6:
            h, s, b, an, ae, dt = parts[:6]
            match = re.search(r"Merge pull request #(\d+) from (.+)", s)
            if match:
                pr_num = int(match.group(1))
                clean_t = b.strip().splitlines()[0] if b.strip() else s

                if matcher(author, name=an, email=ae):
                    if not any(r.pr_number == pr_num for r in local_reviews):
                        local_reviews.append(
                            ReviewItem(
                                {
                                    "pr_number": pr_num,
                                    "pr_title": clean_t,
                                    "reviewer": author,
                                    "state": "APPROVED",
                                    "submitted_at": dt,
                                }
                            )
                        )
                elif f"Reviewed-by: {author}" in b or f"Approved-by: {author}" in b:
                    if not any(r.pr_number == pr_num for r in local_reviews):
                        local_reviews.append(
                            ReviewItem(
                                {
                                    "pr_number": pr_num,
                                    "pr_title": clean_t,
                                    "reviewer": author,
                                    "state": "APPROVED",
                                    "submitted_at": dt,
                                }
                            )
                        )
                continue

            # Check direct branch merges into dev/main/stage
            branch_match = re.search(
                r"Merge branch '([^']+)' into (dev|main|stage|master)", s
            )
            if branch_match and matcher(author, name=an, email=ae):
                merged_branch = branch_match.group(1).split("/")[-1]
                if merged_branch not in ("dev", "main", "stage", "master"):
                    clean_t = (
                        b.strip().splitlines()[0]
                        if b.strip()
                        else f"Merged branch {merged_branch}"
                    )
                    if not any(r.get("pr_title") == clean_t for r in local_reviews):
                        local_reviews.append(
                            ReviewItem(
                                {
                                    "pr_number": 0,
                                    "pr_title": clean_t,
                                    "reviewer": author,
                                    "state": "APPROVED",
                                    "submitted_at": dt,
                                }
                            )
                        )

    return local_reviews
