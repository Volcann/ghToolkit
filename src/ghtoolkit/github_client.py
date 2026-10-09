"""GitHub API and Local Git Client.

Provides unified methods to retrieve commits, pull requests, reviews, and branches
from local Git repositories, GitHub CLI (`gh`), or GitHub REST API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import requests

from .models import CommitInfo, PullRequestInfo, ReviewInfo
from .utils import clean_commit_message, format_iso_date, is_merge_commit

logger = logging.getLogger(__name__)


def is_author_match(
    target_author: str,
    name: str = "",
    email: str = "",
    login: str = "",
) -> bool:
    """Check if git author name, email, or login matches the target author."""
    t = target_author.strip().lower()
    targets = {t}
    # Match user aliases for Volcann / Mohsin Ali
    if t in ("volcann", "mohsin ali", "mohsin"):
        targets.update(
            {"volcann", "mohsin ali", "mohsin", "mohsinmuhammad823@gmail.com"}
        )

    name_lower = name.strip().lower()
    email_lower = email.strip().lower()
    login_lower = login.strip().lower()

    for item in targets:
        if (
            item in name_lower
            or item in email_lower
            or item in login_lower
            or (name_lower and name_lower in item)
            or (login_lower and login_lower in item)
        ):
            return True
    return False


class GitHubClient:
    """Client for querying GitHub data via local Git repositories, `gh` CLI, or REST API."""

    def __init__(
        self,
        token: str | None = None,
        timeout: int = 30,
        prefer_cli: bool = True,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.timeout = timeout
        self.has_gh_cli = prefer_cli and (shutil.which("gh") is not None)
        self.session = requests.Session()
        if self.token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github.v3+json",
                }
            )

    # -------------------------------------------------------------------------
    # Local Git Execution
    # -------------------------------------------------------------------------

    def _run_git_command(self, args: list[str], cwd: str) -> str | None:
        """Run a git command in a local repository directory."""
        if not cwd or not os.path.isdir(cwd):
            return None
        cmd = ["git", "-C", cwd, *args]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
            return res.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.debug("git command failed (%s): %s", cmd, e)
            return None

    # -------------------------------------------------------------------------
    # Core CLI & REST Helpers
    # -------------------------------------------------------------------------

    def _run_gh_command(self, args: list[str]) -> Any | None:
        """Run a `gh` command and return parsed JSON stdout, or None on failure."""
        if not self.has_gh_cli:
            return None
        cmd = ["gh", *args]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
            out = res.stdout.strip()
            if not out:
                return None
            return json.loads(out)
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
        ) as e:
            logger.debug("gh command failed (%s): %s", cmd, e)
            return None

    def _rest_get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> Any | None:
        """Query GitHub REST API with session headers."""
        url = f"https://api.github.com/{endpoint.lstrip('/')}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            logger.debug("GitHub REST API error %s: %s", resp.status_code, resp.text)
            return None
        except Exception as e:
            logger.debug("GitHub REST API exception for %s: %e", url, e)
            return None

    # -------------------------------------------------------------------------
    # Commits
    # -------------------------------------------------------------------------

    def get_user_commits_for_date(
        self,
        owner: str,
        repo: str,
        author: str,
        target_date: date,
        local_path: str = "",
    ) -> list[CommitInfo]:
        """Fetch commits authored by `author` on `target_date`."""
        iso_date = format_iso_date(target_date)

        # 1. Try local git repository if available
        if local_path and os.path.isdir(local_path):
            from datetime import datetime, timedelta, timezone

            prev_date = target_date - timedelta(days=1)
            next_date = target_date + timedelta(days=1)
            git_out = self._run_git_command(
                [
                    "log",
                    f"--since={prev_date.isoformat()}T12:00:00",
                    f"--until={next_date.isoformat()}T12:00:00",
                    "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
                    "--all",
                ],
                cwd=local_path,
            )
            if git_out:
                local_commits: list[CommitInfo] = []
                for record in git_out.strip().split("\x1e"):
                    record = record.strip()
                    if not record:
                        continue
                    parts = record.split("\x1f")
                    if len(parts) >= 6:
                        h, s, b, an, ae, dt = parts[:6]
                        dt_clean = dt.strip()
                        if is_merge_commit(s):
                            continue
                        if not is_author_match(author, name=an, email=ae):
                            continue

                        # Match if commit occurred on target_date in either local timezone OR in UTC
                        try:
                            commit_dt = datetime.fromisoformat(dt_clean)
                            if (
                                commit_dt.date() != target_date
                                and commit_dt.astimezone(timezone.utc).date()
                                != target_date
                            ):
                                continue
                        except Exception:
                            if not dt_clean.startswith(iso_date):
                                continue

                        # Try to extract branch or PR reference
                        branch_name = None
                        branch_out = self._run_git_command(
                            ["branch", "--contains", h], cwd=local_path
                        )
                        if branch_out:
                            branches = [
                                b.strip().lstrip("* ")
                                for b in branch_out.strip().splitlines()
                                if b.strip() and not b.strip().startswith("(")
                            ]
                            if branches:
                                branch_name = branches[0]

                        commit_files: list[str] = []
                        files_out = self._run_git_command(
                            ["diff-tree", "--no-commit-id", "--name-only", "-r", h],
                            cwd=local_path,
                        )
                        if files_out:
                            commit_files = [
                                f.strip() for f in files_out.splitlines() if f.strip()
                            ]

                        local_commits.append(
                            CommitInfo(
                                sha=h,
                                message=f"{s}\n\n{b}".strip(),
                                author_name=an,
                                author_login=author,
                                date=dt_clean,
                                branch=branch_name,
                                files=commit_files,
                            )
                        )
                if local_commits:
                    return local_commits

        # 2. Try gh api
        since = f"{iso_date}T00:00:00Z"
        until = f"{iso_date}T23:59:59Z"
        commits_raw = None

        if self.has_gh_cli:
            api_endpoint = f"repos/{owner}/{repo}/commits?author={author}&since={since}&until={until}&per_page=100"
            commits_raw = self._run_gh_command(["api", api_endpoint])

        # 3. Try REST API fallback
        if commits_raw is None:
            commits_raw = self._rest_get(
                f"repos/{owner}/{repo}/commits",
                {"author": author, "since": since, "until": until, "per_page": 100},
            )

        if not isinstance(commits_raw, list):
            return []

        results: list[CommitInfo] = []
        for item in commits_raw:
            if not isinstance(item, dict):
                continue
            sha = item.get("sha", "")
            commit_data = item.get("commit", {})
            msg = commit_data.get("message", "")

            if is_merge_commit(msg):
                continue

            author_data = commit_data.get("author", {})
            author_login = ""
            if item.get("author"):
                author_login = item["author"].get("login", "")
            if not author_login:
                author_login = author_data.get("name", author)

            commit_date = author_data.get("date", "")
            url = item.get("html_url", "")

            results.append(
                CommitInfo(
                    sha=sha,
                    message=msg,
                    author_name=author_data.get("name", ""),
                    author_login=author_login,
                    date=commit_date,
                    url=url,
                )
            )

        return results

    # -------------------------------------------------------------------------
    # Pull Requests
    # -------------------------------------------------------------------------

    def get_user_prs_for_date(
        self,
        owner: str,
        repo: str,
        author: str,
        target_date: date,
        local_path: str = "",
    ) -> list[PullRequestInfo]:
        """Fetch pull requests created or merged on `target_date`."""
        iso_date = format_iso_date(target_date)

        # 1. Try local git merge commits inspection
        if local_path and os.path.isdir(local_path):
            merge_out = self._run_git_command(
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
            if merge_out:
                local_prs: list[PullRequestInfo] = []
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

                        # Inspect commits inside this merged PR branch
                        pr_commits_out = self._run_git_command(
                            [
                                "log",
                                f"{h}^1..{h}^2",
                                "--format=%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
                            ],
                            cwd=local_path,
                        )
                        commits_list: list[CommitInfo] = []
                        primary_title = b.strip().splitlines()[0] if b.strip() else ""

                        if pr_commits_out:
                            for c_line in pr_commits_out.strip().split("\n"):
                                if not c_line:
                                    continue
                                c_parts = c_line.split("\x1f")
                                if len(c_parts) >= 6:
                                    ch, cs, cb, can, cae, cdt = c_parts[:6]
                                    if is_merge_commit(cs):
                                        continue
                                    if not primary_title:
                                        primary_title = cs
                                    is_match = is_author_match(
                                        author, name=can, email=cae
                                    )
                                    commits_list.append(
                                        CommitInfo(
                                            sha=ch,
                                            message=f"{cs}\n\n{cb}".strip(),
                                            author_name=can,
                                            author_login=can
                                            if not is_match
                                            else author,
                                            date=cdt,
                                            pr_number=pr_num,
                                        )
                                    )

                        # Clean title
                        if not primary_title:
                            primary_title = branch_raw

                        # A commit inside a PR does not establish ownership of the
                        # PR. Confirm the PR author with GitHub before classifying
                        # this as the configured contributor's own PR.
                        pr_data = None
                        if self.has_gh_cli:
                            pr_data = self._run_gh_command(
                                [
                                    "pr",
                                    "view",
                                    str(pr_num),
                                    "--repo",
                                    f"{owner}/{repo}",
                                    "--json",
                                    "author",
                                ]
                            )
                        if pr_data is None:
                            pr_data = self._rest_get(
                                f"repos/{owner}/{repo}/pulls/{pr_num}"
                            )

                        pr_author = ""
                        if isinstance(pr_data, dict):
                            author_data = pr_data.get("author") or pr_data.get("user")
                            if isinstance(author_data, dict):
                                pr_author = author_data.get("login", "")

                        if pr_author and is_author_match(author, login=pr_author):
                            local_prs.append(
                                PullRequestInfo(
                                    number=pr_num,
                                    title=primary_title,
                                    body=b.strip(),
                                    author_login=pr_author,
                                    state="MERGED",
                                    created_at=dt,
                                    head_ref=branch_raw,
                                    is_own=True,
                                    commits=commits_list,
                                    repo_name=repo,
                                )
                            )
                if local_prs:
                    return local_prs

        # 2. Try GitHub CLI
        search_query = f"repo:{owner}/{repo} author:{author} type:pr created:{iso_date}"
        prs_raw = None

        if self.has_gh_cli:
            prs_raw = self._run_gh_command(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--state",
                    "all",
                    "--search",
                    f"author:{author} created:{iso_date}",
                    "--json",
                    "number,title,body,author,state,url,createdAt,headRefName,commits",
                ]
            )

        # 3. Try REST API fallback
        if prs_raw is None:
            search_res = self._rest_get("search/issues", {"q": search_query})
            if isinstance(search_res, dict) and "items" in search_res:
                prs_raw = search_res["items"]

        if not isinstance(prs_raw, list):
            return []

        prs: list[PullRequestInfo] = []
        for item in prs_raw:
            if not isinstance(item, dict):
                continue
            pr_num = item.get("number")
            if not pr_num:
                continue

            title = item.get("title", "")
            body = item.get("body", "") or ""
            author_login = ""
            if isinstance(item.get("author"), dict):
                author_login = item["author"].get("login", "")
            elif isinstance(item.get("user"), dict):
                author_login = item["user"].get("login", "")

            state = item.get("state", "OPEN")
            url = item.get("html_url") or item.get("url", "")
            created_at = item.get("created_at") or item.get("createdAt", "")
            head_ref = item.get("headRefName", "") or (
                item.get("head", {}).get("ref", "")
                if isinstance(item.get("head"), dict)
                else ""
            )

            commits_list: list[CommitInfo] = []
            if "commits" in item and isinstance(item["commits"], list):
                for c in item["commits"]:
                    if not isinstance(c, dict):
                        continue
                    c_sha = c.get("oid") or c.get("sha", "")
                    c_msg = c.get("messageHeadline") or c.get("message", "")
                    c_auth = ""
                    if (
                        c.get("authors")
                        and isinstance(c["authors"], list)
                        and c["authors"]
                    ):
                        c_auth = c["authors"][0].get("login") or c["authors"][0].get(
                            "name", ""
                        )
                    elif c.get("author") and isinstance(c["author"], dict):
                        c_auth = c["author"].get("login") or c["author"].get("name", "")
                    commits_list.append(
                        CommitInfo(
                            sha=c_sha,
                            message=c_msg,
                            author_login=c_auth,
                            pr_number=pr_num,
                        )
                    )

            prs.append(
                PullRequestInfo(
                    number=pr_num,
                    title=title,
                    body=body,
                    author_login=author_login,
                    state=state,
                    url=url,
                    created_at=created_at,
                    head_ref=head_ref,
                    is_own=author_login.lower() == author.lower()
                    if author_login
                    else True,
                    commits=commits_list,
                    repo_name=repo,
                )
            )

        return prs

    def get_pr_details(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        local_path: str = "",
        author: str = "",
    ) -> PullRequestInfo | None:
        """Fetch full details and commits of a single pull request."""
        # 1. Try local git merge commit inspection
        if local_path and os.path.isdir(local_path):
            git_out = self._run_git_command(
                [
                    "log",
                    f"--grep=Merge pull request #{pr_number} ",
                    "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
                    "-n",
                    "1",
                    "--all",
                ],
                cwd=local_path,
            )
            if git_out and git_out.strip():
                parts = git_out.strip().lstrip("\x1e").split("\x1f")
                if len(parts) >= 6:
                    h, s, b, an, ae, dt = parts[:6]
                    commits_out = self._run_git_command(
                        [
                            "log",
                            f"{h}^1..{h}^2",
                            "--format=%x1e%H%x1f%s%x1f%b%x1f%an%x1f%ae%x1f%aI",
                        ],
                        cwd=local_path,
                    )
                    commits_list: list[CommitInfo] = []
                    primary_title = ""
                    if commits_out:
                        for cl in commits_out.strip().split("\x1e"):
                            cl = cl.strip()
                            if not cl:
                                continue
                            cp = cl.split("\x1f")
                            if len(cp) >= 6:
                                ch, cs, cb, can, cae, cdt = cp[:6]
                                commit_files: list[str] = []
                                c_files_out = self._run_git_command(
                                    [
                                        "diff-tree",
                                        "--no-commit-id",
                                        "--name-only",
                                        "-r",
                                        ch,
                                    ],
                                    cwd=local_path,
                                )
                                if c_files_out:
                                    commit_files = [
                                        f.strip()
                                        for f in c_files_out.splitlines()
                                        if f.strip()
                                    ]

                                commits_list.append(
                                    CommitInfo(
                                        sha=ch,
                                        message=f"{cs}\n\n{cb}".strip(),
                                        author_name=can,
                                        author_login=can,
                                        date=cdt,
                                        pr_number=pr_number,
                                        files=commit_files,
                                    )
                                )
                    if b.strip():
                        primary_title = b.strip().splitlines()[0]
                    elif commits_list:
                        primary_title = commits_list[0].headline
                    if not primary_title:
                        primary_title = s

                    m_branch = re.search(r"Merge pull request #\d+ from (.+)", s)
                    head_ref = m_branch.group(1).strip() if m_branch else ""

                    pr_files: list[str] = []
                    pr_files_out = self._run_git_command(
                        ["diff", "--name-only", f"{h}^1...{h}^2"],
                        cwd=local_path,
                    )
                    if pr_files_out:
                        pr_files = [
                            f.strip() for f in pr_files_out.splitlines() if f.strip()
                        ]

                    pr_author = an
                    if head_ref:
                        ref_parts = [
                            p.upper()
                            for p in head_ref.replace("/", "-").split("-")
                            if p
                        ]
                        if "MM" in ref_parts:
                            pr_author = author or "Volcann"
                        elif "MB" in ref_parts:
                            pr_author = "Moin Bukhari"
                        elif "TS" in ref_parts:
                            pr_author = "Tayyab Sami"
                        elif "UM" in ref_parts:
                            pr_author = "Uzair Maqsood"

                    if pr_author == an and commits_list:
                        c_authors = [
                            c.author_name for c in commits_list if c.author_name
                        ]
                        if c_authors and author:
                            if all(
                                is_author_match(author, name=ca) for ca in c_authors
                            ):
                                pr_author = author

                    is_own_pr = (
                        is_author_match(author, login=pr_author, name=pr_author)
                        if author
                        else True
                    )

                    return PullRequestInfo(
                        number=pr_number,
                        title=primary_title,
                        body=b.strip(),
                        author_login=pr_author,
                        state="MERGED",
                        created_at=dt,
                        head_ref=head_ref,
                        is_own=is_own_pr,
                        commits=commits_list,
                        repo_name=repo,
                        files_changed=pr_files,
                    )

        # 2. Try GitHub CLI / API
        data = None
        if self.has_gh_cli:
            data = self._run_gh_command(
                [
                    "pr",
                    "view",
                    str(pr_number),
                    "--repo",
                    f"{owner}/{repo}",
                    "--json",
                    "number,title,body,author,state,url,createdAt,headRefName,commits",
                ]
            )

        if data is None:
            data = self._rest_get(f"repos/{owner}/{repo}/pulls/{pr_number}")

        if not isinstance(data, dict):
            return None

        title = data.get("title", "")
        body = data.get("body", "") or ""
        author_login = ""
        if isinstance(data.get("author"), dict):
            author_login = data["author"].get("login", "")
        elif isinstance(data.get("user"), dict):
            author_login = data["user"].get("login", "")

        state = data.get("state", "OPEN")
        url = data.get("html_url") or data.get("url", "")
        created_at = data.get("created_at") or data.get("createdAt", "")
        head_ref = data.get("headRefName", "") or (
            data.get("head", {}).get("ref", "")
            if isinstance(data.get("head"), dict)
            else ""
        )

        commits_list: list[CommitInfo] = []
        raw_commits = data.get("commits")
        if raw_commits is None:
            raw_commits = self._rest_get(
                f"repos/{owner}/{repo}/pulls/{pr_number}/commits"
            )

        if isinstance(raw_commits, list):
            for c in raw_commits:
                if not isinstance(c, dict):
                    continue
                c_sha = c.get("oid") or c.get("sha", "")
                c_msg = c.get("messageHeadline") or (
                    c.get("commit", {}).get("message", "")
                    if isinstance(c.get("commit"), dict)
                    else ""
                )
                c_auth = ""
                if c.get("authors") and isinstance(c["authors"], list) and c["authors"]:
                    c_auth = c["authors"][0].get("login") or c["authors"][0].get(
                        "name", ""
                    )
                elif c.get("author") and isinstance(c["author"], dict):
                    c_auth = c["author"].get("login") or c["author"].get("name", "")

                commits_list.append(
                    CommitInfo(
                        sha=c_sha,
                        message=clean_commit_message(c_msg),
                        author_login=c_auth,
                        pr_number=pr_number,
                    )
                )

        return PullRequestInfo(
            number=pr_number,
            title=title,
            body=body,
            author_login=author_login,
            state=state,
            url=url,
            created_at=created_at,
            head_ref=head_ref,
            commits=commits_list,
            repo_name=repo,
        )

    # -------------------------------------------------------------------------
    # Associated Pull Requests for a Commit
    # -------------------------------------------------------------------------

    def get_commit_pull_requests(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
        local_path: str = "",
    ) -> list[dict[str, Any]]:
        """Find pull requests associated with a commit SHA."""
        # 1. Try local git merge ancestry inspection
        if local_path and os.path.isdir(local_path):
            ancestry_out = ""
            for ref in ["origin/dev", "dev", "origin/main", "main", "HEAD"]:
                out = self._run_git_command(
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
                    line
                    for line in ancestry_out.splitlines()
                    if "Merge pull request #" in line
                ]
                if pr_matches:
                    earliest_pr = pr_matches[-1]
                    m = re.search(r"Merge pull request #(\d+)", earliest_pr)
                    if m:
                        return [{"number": int(m.group(1))}]

            # Also check if commit message contains a PR reference (#384)
            c_msg = self._run_git_command(
                ["log", "-n", "1", "--format=%s", commit_sha], cwd=local_path
            )
            if c_msg:
                m_num = re.search(r"#(\d+)", c_msg)
                if m_num:
                    return [{"number": int(m_num.group(1))}]

        # 2. Try gh api
        pulls = None
        if self.has_gh_cli:
            pulls = self._run_gh_command(
                ["api", f"repos/{owner}/{repo}/commits/{commit_sha}/pulls"]
            )

        if pulls is None:
            pulls = self._rest_get(f"repos/{owner}/{repo}/commits/{commit_sha}/pulls")

        return pulls if isinstance(pulls, list) else []

    def get_commit_branch(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
        commit_message: str = "",
        local_path: str = "",
    ) -> str:
        """Find the most relevant branch name for a commit SHA."""
        if local_path and os.path.isdir(local_path):
            branch_out = self._run_git_command(
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
                    if b
                    not in (
                        "dev",
                        "stage",
                        "main",
                        "master",
                        "origin/dev",
                        "origin/stage",
                    )
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

    # -------------------------------------------------------------------------
    # Reviews
    # -------------------------------------------------------------------------

    def get_user_reviewed_prs_for_date(
        self,
        owner: str,
        repo: str,
        author: str,
        target_date: date,
        local_path: str = "",
    ) -> list[ReviewInfo]:
        """Find pull requests where `author` reviewed or merged on `target_date`."""
        iso_date = format_iso_date(target_date)

        # 1. Try local git merge commits where author is merger but not commit author
        if local_path and os.path.isdir(local_path):
            merge_out = self._run_git_command(
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
            if merge_out:
                local_reviews: list[ReviewInfo] = []
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

                            # Check if merger is the target author
                            if is_author_match(author, name=an, email=ae):
                                clean_t = b.strip().splitlines()[0] if b.strip() else s
                                # Avoid duplicates
                                if not any(
                                    r.pr_number == pr_num for r in local_reviews
                                ):
                                    local_reviews.append(
                                        ReviewInfo(
                                            pr_number=pr_num,
                                            pr_title=clean_t,
                                            reviewer=author,
                                            state="APPROVED",
                                            submitted_at=dt,
                                        )
                                    )
                            else:
                                # Also check if author submitted an approval in commit trailers / comments
                                if (
                                    f"Reviewed-by: {author}" in b
                                    or f"Approved-by: {author}" in b
                                ):
                                    clean_t = (
                                        b.strip().splitlines()[0] if b.strip() else s
                                    )
                                    if not any(
                                        r.pr_number == pr_num for r in local_reviews
                                    ):
                                        local_reviews.append(
                                            ReviewInfo(
                                                pr_number=pr_num,
                                                pr_title=clean_t,
                                                reviewer=author,
                                                state="APPROVED",
                                                submitted_at=dt,
                                            )
                                        )
                            continue

                        # Check direct branch merges into dev/main/stage
                        branch_match = re.search(
                            r"Merge branch '([^']+)' into (dev|main|stage|master)", s
                        )
                        if branch_match and is_author_match(author, name=an, email=ae):
                            merged_branch = branch_match.group(1).split("/")[-1]
                            # Ignore standard base sync merges like dev into dev
                            if merged_branch not in ("dev", "main", "stage", "master"):
                                clean_t = (
                                    b.strip().splitlines()[0]
                                    if b.strip()
                                    else f"Merged branch {merged_branch}"
                                )
                                if not any(
                                    r.pr_title == clean_t for r in local_reviews
                                ):
                                    local_reviews.append(
                                        ReviewInfo(
                                            pr_number=0,
                                            pr_title=clean_t,
                                            reviewer=author,
                                            state="APPROVED",
                                            submitted_at=dt,
                                        )
                                    )
                if local_reviews:
                    return local_reviews

        # 2. Try GitHub CLI / API
        reviewed_prs: list[ReviewInfo] = []
        search_prs = None

        if self.has_gh_cli:
            search_prs = self._run_gh_command(
                [
                    "pr",
                    "list",
                    "--repo",
                    f"{owner}/{repo}",
                    "--state",
                    "all",
                    "--search",
                    f"reviewed-by:{author} updated:{iso_date}",
                    "--json",
                    "number,title,url",
                ]
            )

        if search_prs is None:
            q = f"repo:{owner}/{repo} type:pr reviewed-by:{author} updated:{iso_date}"
            res = self._rest_get("search/issues", {"q": q})
            if isinstance(res, dict) and "items" in res:
                search_prs = res["items"]

        if not isinstance(search_prs, list):
            return []

        for pr in search_prs:
            pr_num = pr.get("number")
            pr_title = pr.get("title", "")
            pr_url = pr.get("url") or pr.get("html_url", "")
            if not pr_num:
                continue

            reviews = None
            if self.has_gh_cli:
                reviews = self._run_gh_command(
                    ["api", f"repos/{owner}/{repo}/pulls/{pr_num}/reviews"]
                )
            if reviews is None:
                reviews = self._rest_get(f"repos/{owner}/{repo}/pulls/{pr_num}/reviews")

            if isinstance(reviews, list):
                for r in reviews:
                    if not isinstance(r, dict):
                        continue
                    r_user = r.get("user", {}).get("login", "")
                    submitted_at = r.get("submitted_at", "")
                    if r_user.lower() == author.lower() and submitted_at.startswith(
                        iso_date
                    ):
                        reviewed_prs.append(
                            ReviewInfo(
                                pr_number=pr_num,
                                pr_title=pr_title,
                                reviewer=author,
                                state=r.get("state", "COMMENTED"),
                                submitted_at=submitted_at,
                                url=pr_url,
                            )
                        )
                        break
            else:
                reviewed_prs.append(
                    ReviewInfo(
                        pr_number=pr_num,
                        pr_title=pr_title,
                        reviewer=author,
                        state="REVIEWED",
                        submitted_at=iso_date,
                        url=pr_url,
                    )
                )

        return reviewed_prs

    # -------------------------------------------------------------------------
    # Comments & Review Discussion
    # -------------------------------------------------------------------------

    def get_pr_user_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        author: str,
        target_date: date | None = None,
        local_path: str = "",
    ) -> list[str]:
        """Fetch discussion and review comments posted by author on a PR for target_date.

        Checks:
        1. Local comments cache file (.cache/pr_comments.json).
        2. GitHub CLI `gh api repos/{owner}/{repo}/issues/{pr_number}/comments`.
        3. GitHub REST API.
        """
        iso_prefix = format_iso_date(target_date) if target_date else ""
        comments_found: list[str] = []

        cache_file = Path(".cache/pr_comments.json")
        cached_data: dict[str, Any] = {}
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
            except Exception:
                pass

        repo_key = f"{owner}/{repo}"
        pr_key = str(pr_number)
        if repo_key in cached_data and pr_key in cached_data[repo_key]:
            for item in cached_data[repo_key][pr_key]:
                c_auth = item.get("author", "")
                c_date = item.get("created_at", "")
                c_body = item.get("body", "").strip()
                if is_author_match(author, login=c_auth):
                    if not iso_prefix or c_date.startswith(iso_prefix):
                        if c_body and c_body not in comments_found:
                            comments_found.append(c_body)

            if not comments_found:
                for item in cached_data[repo_key][pr_key]:
                    c_auth = item.get("author", "")
                    c_body = item.get("body", "").strip()
                    if is_author_match(author, login=c_auth):
                        if c_body and c_body not in comments_found:
                            comments_found.append(c_body)

        # 2. Try GitHub CLI / API (issues comments, inline review comments, and review bodies)
        endpoints = [
            f"repos/{owner}/{repo}/issues/{pr_number}/comments",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments",
            f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        ]

        new_cache_entries = []
        for ep in endpoints:
            raw_data = None
            if self.has_gh_cli:
                raw_data = self._run_gh_command(["api", ep])
            if raw_data is None:
                raw_data = self._rest_get(ep)

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

                    if is_author_match(author, login=user_login):
                        if not iso_prefix or c_date.startswith(iso_prefix):
                            if c_body not in comments_found:
                                comments_found.append(c_body)

        if not comments_found and new_cache_entries:
            for item in new_cache_entries:
                if is_author_match(author, login=item["author"]):
                    if item["body"] not in comments_found:
                        comments_found.append(item["body"])

        if new_cache_entries:
            cached_data.setdefault(repo_key, {})[pr_key] = new_cache_entries
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cached_data, f, indent=2)
            except Exception:
                pass

        return comments_found
