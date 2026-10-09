# ghToolkit

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: 146 passed](https://img.shields.io/badge/tests-146%20passed-brightgreen.svg)](https://docs.python.org/3/library/unittest.html)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-standard%20library%20only-purple.svg)](https://docs.python.org/3/)
[![Tooling: uv](https://img.shields.io/badge/tooling-uv-purple.svg)](https://github.com/astral-sh/uv)

**Unified GitHub CLI Facade & High-Performance Git Acceleration Engine.**  
_Connect once to GitHub. Power scripts, PR reviewers, status reporters, and AI agents with sub-10ms local acceleration and zero external dependencies._

[Quick Start](#-quickstart--installation) · [The Problem](#the-problem) · [The Developer Time Problem](#the-developer-time-problem) · [What ghToolkit Does](#what-ghtoolkit-does) · [Key Features](#-key-features) · [Architecture](#-architecture--ecosystem-unification) · [Client Usage](#-client-usage--recipes) · [Ecosystem Migration](#-consumer-migration-guide) · [Makefile Reference](#-makefile-reference)

---

## The Problem

Prior to `ghToolkit`, three independent internal projects maintained separate, fragmented, and brittle implementations to interact with GitHub:

1. **`lazy-reviewer`**: Maintained an ad-hoc 146-line subprocess script prone to shell quoting bugs on multi-line review bodies, unescaped markdown suggestion blocks, and zero caching.
2. **`workedTask`**: Maintained a monolithic 1,083-line client mixing raw REST calls (`requests`), local `git -C` commands, and CLI invocations without clean separation, duplicating author alias lists and date filtering.
3. **`volcanai`**: Maintained scattered scripts across cron jobs making sequential, unbatched API calls that repeatedly hit GitHub rate limits, suffered from N+1 subprocess latency, and lacked coordinated crash recovery.

Whenever an engineer needed to fetch a PR diff, extract contributor commits, or submit a review, they had to reinvent the wheel:

```text
Engineer / New Agent Tool
   │
   ├── Write custom subprocess call to `gh`
   ├── Debug shell escaping for multiline review text & backticks
   ├── Deal with GitHub REST 250-commit and 1,000-search pagination caps
   ├── Suffer 3–10s network roundtrips for local repository queries
   ├── Reconstruct author aliases (e.g., handles vs. commit emails)
   ├── Hit GitHub API rate limits during repeated runs
   └── Fix broken code when GitHub CLI output formatting changes
```

### Why fragmented implementations become painful

- **Maintenance Nightmare**: When GitHub CLI formatting changed or an API endpoint shifted, fixes had to be duplicated across three separate codebases.
- **Vulnerability to Shell Bugs**: Passing multiline reviews and code suggestions directly through shell arguments risked command truncation and quoting failures.
- **Sluggish Performance**: Making sequential remote API calls over the network when a local Git clone already existed on disk turned sub-second operations into multi-minute bottlenecks.
- **Inconsistent Data Formats**: One tool returned raw untyped dictionaries, another returned custom dataclasses, and a third returned tuples.

> **The problem isn't GitHub's API. The problem is having every tool, agent, and script maintain its own fragile, un-cached GitHub integration from scratch.**

---

## The Developer Time Problem

This is the primary reason `ghToolkit` exists.

Without a unified toolkit:

```text
Developer
   │
   ├── Fix shell quoting bug in lazy-reviewer
   ├── Debug API rate limit in volcanai
   ├── Maintain 1,083-line monolithic client in workedTask
   ├── Re-implement author alias resolution for new script
   ├── Re-write diff preservation logic for PR reviewer
   └── Repeat for every new project...
```

With `ghToolkit`:

```text
Developer
   │
   └── Import ghToolkit once
              │
              ▼
        Unified Facade
              │
        ┌─────┼─────┐
        ▼     ▼     ▼
  lazy-reviewer  workedTask  volcanai
        │     │     │
        └─────┼─────┘
              ▼
  Sub-10ms Local Git + Standard CLI
```

### Measurable Engineering Impact

- **Hours of Repetitive Maintenance Saved**: Replaced 2,000+ lines of duplicated, fragile plumbing with one hardened, tested library.
- **Sub-10ms Local Git Acceleration**: Automatically routes operations through `git -C` when a local clone is present, turning multi-second network round-trips into instantaneous disk queries.
- **Zero Runtime Dependencies**: Operates 100% on Python's standard library (>= 3.11) + the installed `gh` CLI. Zero dependency rot, zero virtualenv bloat.
- **Rate-Limit Immunity**: Disk-backed atomic comment caching (`.cache/pr_comments.json`) and resumable audit queues (`progress.txt`) eliminate redundant API burns.

---

## What ghToolkit Does

`ghToolkit` provides a high-level, unified object-oriented facade (`GitHubClient`) over the GitHub CLI and local Git repositories.

Instead of hand-rolling subprocess commands or maintaining heavy third-party SDK dependencies, your application connects to `ghToolkit`:

1. **Discovers Local vs. Remote Path**: Queries local Git history via `git -C` for sub-10ms lookups, falling back to authenticated `gh` CLI commands when local clones are unavailable.
2. **Normalizes Author Identity**: Maps usernames, full names, and git commit emails through a centralized alias registry.
3. **Preserves Byte-Exact Diffs**: Writes raw patches (`changes.diff`) and syntax-highlighted markdown (`changes.md`) to isolated directories with zero truncation.
4. **Handles Pagination & API Caps**: Automatically overcomes GitHub's 250-commit and 1,000-search limits using slurped GraphQL pagination and local windowing.
5. **Ensures Injection Safety**: Writes comments and review payloads via stdin and temporary files, preventing shell escaping issues.
6. **Caches Discussions & Audits**: Persists comments atomically to disk and provides crash-proof queue processing for long-running batch audits.

> **Build the GitHub integration once. Use it everywhere across CLIs, automated reviewers, daily status reporters, and AI agents.**

---

## 🌟 Key Features

1. **Hybrid Execution Engine (Sub-10ms Local Git)**:
   - When a local clone (`local_repo_path`) is supplied, uses optimized `git -C` commands (`git log`, `git diff-tree`, `git branch --contains`).
   - Seamlessly falls back to authenticated GitHub CLI calls (`gh api`, `gh pr list`, `gh pr view`).
2. **Zero Third-Party Runtime Dependencies**:
   - Requires only Python standard library (>= 3.11) and the system's `gh` executable.
   - No `requests`, no `urllib3`, no heavy cloud SDKs.
3. **Transparent Hybrid DTOs**:
   - `CommitItem`, `PullRequestItem`, and `ReviewItem` inherit directly from standard `dict`.
   - Legacy code can use dictionary lookups (`item["number"]`), while modern code accesses typed attributes (`item.number`, `item.author_login`, `item.commits`).
4. **Author Identity & Alias Resolution**:
   - Maps contributor handles, display names, and commit emails (`AuthorRegistry`) so commits are never misattributed.
5. **Exact Diff Preservation**:
   - Writes byte-accurate `.diff` patches and Markdown `.md` artifacts into isolated `temp/` subdirectories.
   - Preserves whitespace, CRLF, binary flags, and backtick code fences without mutation.
6. **Multi-Source Comment Aggregation & Disk Caching**:
   - Unifies issue comments, inline code review threads, and top-level review summaries.
   - Uses atomic disk caching (`.cache/pr_comments.json`) to prevent API throttling during repeated runs.
7. **High-Throughput Auditing & Resumable Queues**:
   - Scans thousands of repository PRs using multithreading to discover foreign contributions and author commits.
   - Provides an atomic, file-backed queue (`progress.txt`) for long-running audit jobs with automatic crash resumption.
8. **Timezone-Aware Date Windows**:
   - Computes half-open local calendar intervals (e.g., `Asia/Karachi` or `UTC`) and normalizes daylight saving transitions.

---

## 🚀 Quickstart & Installation

### Using `uv` (Recommended)

```bash
# Clone the repository
git clone https://github.com/Volcann/ghToolkit.git
cd ghToolkit

# Sync environment
uv sync --locked

# Authenticate GitHub CLI (if not already authenticated)
gh auth login
gh auth status

# Run the test suite (146 tests in ~0.6s)
uv run python -m unittest discover -s tests -v
```

### Using standard `pip`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

gh auth login
python3 -m unittest discover -s tests -v
```

---

## 🏛 Architecture & Ecosystem Unification

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                           CONSUMER APPLICATIONS                           │
│     lazy-reviewer           workedTask (Status)           volcanai        │
└──────────────┬───────────────────────┬────────────────────────┬───────────┘
               │                       │                        │
               ▼                       ▼                        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                       GitHubClient (Unified Facade)                       │
│                     (src/ghtoolkit/github_client.py)                      │
└───────┬───────────────────┬───────────────────┬───────────────────┬───────┘
        │                   │                   │                   │
        ▼                   ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Git Local    │   │   Identity    │   │   Comments    │   │  Audit Engine │
│ Acceleration  │   │  & Aliases    │   │  & Disk Cache │   │  & Progress   │
│  (git_local)  │   │  (identity)   │   │  (comments)   │   │    (audit)    │
└───────┬───────┘   └───────────────┘   └───────────────┘   └───────────────┘
        │
        ▼ (Local clone present? Fast path via `git -C`)
┌───────────────────────────────────────────────────────────────────────────┐
│                         GhAPI & GhRunner (Adapter)                        │
│            (src/ghtoolkit/api.py, runner.py, diff_store.py)               │
└────────────────────────────────────────────────┬──────────────────────────┘
                                                 │
                                                 ▼
                                           GitHub Server
```

---

## 💻 Client Usage & Recipes

### 1. Initialize the Client

```python
from ghtoolkit import GitHubClient

client = GitHubClient(
    "OWNER/REPO",
    local_repo_path="/path/to/local/clone",  # Optional: enables sub-10ms Git fast path
    timezone="Asia/Karachi",                # Default is UTC
    timeout=30.0,
    temp_dir="temp",
)
```

### 2. Querying Commits

```python
# Query commits for a specific date window
commits = client.get_user_commits_for_date("alice", "2026-10-03", branch="main")

# Commits return minimal, high-speed representations
for c in commits:
    print(c.sha, c.headline)

# Fetch detailed commit payload and associated PRs
details = client.get_commit_details("COMMIT_SHA")
prs = client.get_pulls_for_commit("COMMIT_SHA")
```

### 3. Pull Request Operations

```python
# Query PRs by date and state
created = client.get_prs(date="2026-10-03")
merged = client.get_prs(date="2026-10-03", date_field="merged", state="merged")
by_author = client.get_user_prs_for_date("alice", "2026-10-03")

# Fetch full PR metadata (GraphQL slurped to bypass 250-commit cap)
metadata = client.fetch_pr_metadata(123)
print(metadata.title, metadata.headRefOid, metadata.commits)

# Fetch complete PR details with comments and review threads
details = client.get_pr_details(123)
```

### 4. Raw & Formatted Diffs (Preserved in Temp)

Every diff fetch writes byte-accurate files to a unique, isolated directory:

```python
pr_diff = client.get_pr_diff(123)
commit_diff = client.get_commit_diff("COMMIT_SHA")

print(pr_diff.diff_path)     # Path to raw byte-exact changes.diff
print(pr_diff.markdown_path) # Path to fenced changes.md
print(pr_diff.markdown)      # Formatted markdown block
```

### 5. Reviews, Comments & Disk Caching

```python
# Fetch user reviews submitted on a date
reviews = client.get_user_reviews_for_date("alice", "2026-10-03")

# Fetch user comments across issues, reviews, and threads with disk cache
comments = client.get_pr_user_comments(123, "alice", "2026-10-03", use_cache=True)
```

### 6. Safe Checkout and Write Operations

All write operations use secure stdin/temporary files to prevent shell injection:

```python
# Safe checkout into local clone
client.checkout_pr_branch(123)

# Post top-level comment safely via temporary file
client.post_pr_comment(123, "## Automated Review\nAll checks passed.")

# Submit structured inline code review with suggestions
client.create_pull_request_review(
    123,
    commit_id="COMMIT_SHA",
    comments=[
        {
            "path": "src/utils.py",
            "line": 42,
            "side": "RIGHT",
            "body": "```suggestion\nreturn clean_data\n```",
        }
    ],
    body="Inline suggestions applied.",
    event="COMMENT",
)
```

---

## 🛡 Failure Modes & Exception Hierarchy

All exceptions inherit from `GitHubError` for clean upstream handling:

| Exception | Meaning | Recovery / Cause |
|---|---|---|
| `GhNotInstalledError` | The `gh` executable was not found on `PATH`. | Verify installation and environment `PATH`. |
| `GhExecutionError` | OS permission failure or inaccessible directory. | Check file permissions and working directory. |
| `GhTimeoutError` | Subprocess exceeded the configured timeout limit. | Exposes `timeout`, `stdout`, and `stderr`. |
| `GhCommandError` | Non-zero exit code returned by `gh`. | Exposes `returncode`, `stderr`, and `stdout`. |
| `GhResponseError` | Malformed JSON, unexpected GraphQL error, or changed head. | API payload validation failure. |
| `DiffStorageError` | Failed to write `.diff` or `.md` files to disk. | Disk full or filesystem permissions. |

---

## 🔄 Consumer Migration Guide

### 1. Replacing `lazy-reviewer`

Replace `pr_reviewer/github_client.py`:

```python
from ghtoolkit import GitHubClient

client = GitHubClient("owner/repo", local_repo_path="/path/to/repo")

# 1. Fetch metadata & diff
metadata = client.fetch_pr_metadata(pr_number)
diff_text = client.fetch_pr_diff(pr_number)

# 2. Checkout PR branch locally
client.checkout_pr_branch(pr_number)

# 3. Post summary comment
client.post_pr_comment(pr_number, "Review Summary")

# 4. Post batch inline review comments
client.create_pull_request_review(
    pr_number,
    metadata.headRefOid,
    inline_comments=[
        {"path": "service.py", "line": 42, "side": "RIGHT", "body": "```suggestion\nreturn valid\n```"}
    ],
    body="Automated Review",
    event="COMMENT",
)
```

### 2. Replacing `workedTask`

Replace `status_reporter/github_client.py`:

```python
from ghtoolkit import GitHubClient

client = GitHubClient("owner/repo", local_repo_path="/path/to/local/clone")
client.register_author_alias("Volcann", ["Mohsin Ali", "mohsinmuhammad823@gmail.com"])

# Commits, PRs, and reviews for date window (uses sub-10ms local Git fast path)
commits = client.get_user_commits_for_date("Volcann", "2026-10-09")
prs = client.get_user_prs_for_date("Volcann", "2026-10-09")
reviews = client.get_user_reviewed_prs_for_date("Volcann", "2026-10-09")

# Full PR details and comments with disk caching
pr_details = client.get_pr_details(pr_number, author="Volcann")
comments = client.get_pr_user_comments(pr_number, "Volcann", "2026-10-09", use_cache=True)
```

### 3. Replacing `volcanai`

Replace `cron_job/core/get_pr_commit_numbers.py`, `pull_request_summary.py`, and `commit_summary.py`:

```python
from ghtoolkit import GitHubClient, ProgressQueue

client = GitHubClient("owner/repo")

# High-throughput contributor scanning with foreign PR mining
owned_prs, native_commits = client.scan_contributor_contributions(
    "Volcann", limit=5000, include_foreign=True
)

# Resumable audit queue with automatic crash recovery
queue = ProgressQueue("progress.txt")
queue.save([queue.make_pr_item("owner", "repo", num) for num in owned_prs])
next_task = queue.pop()

# State checking and diff extraction
state = client.get_pr_state(pr_number)
pr_diff = client.fetch_pr_diff(pr_number)
commit_diff = client.fetch_commit_diff(commit_sha)
```

---

## 🧪 Verification & Guarantees

- **146 Automated Unit Tests**: Complete coverage spanning local Git commands, API pagination, GraphQL slurping, comment caching, alias matching, and foreign PR auditing.
- **Sub-Second Execution**: Unit tests execute in **~0.6 seconds** using `FakeRunner` without hitting external network endpoints.
- **Strict POSIX Path Safety**: Enforces path sanitization to prevent directory traversal (`../`) and shell injection when generating diffs or checking out branches.
- **Byte-Exact Patch Preservation**: Preserves raw patches matching `git apply --check` standards.

---

## 📁 Repository Structure

```text
ghToolkit/
├── Makefile                   # Development, testing, and linting workflow
├── pyproject.toml             # Standard PEP 517/621 packaging definitions
├── README.md                  # Comprehensive architectural and usage documentation
├── WHY_IT_EXISTS.md           # In-depth architectural justification & migration spec
├── TEST_RESULTS.txt           # Verified test execution log (146 tests passed)
├── src/
│   └── ghtoolkit/
│       ├── __init__.py        # Public package exports
│       ├── api.py             # GhAPI wrapper over GitHub CLI REST & GraphQL
│       ├── audit.py           # High-throughput contributor mining & ProgressQueue
│       ├── comments.py        # Multi-source comment aggregator & CommentCache
│       ├── commit/            # Commit querying, details, and association service
│       ├── dates.py           # Timezone-aware date parsing and half-open windows
│       ├── diff_store.py      # Preserved raw .diff and .md storage engine
│       ├── errors.py          # Typed exception hierarchy
│       ├── git_local.py       # High-speed local git -C command acceleration
│       ├── github_client.py   # Unified facade coordinating all subsystems
│       ├── identity.py        # Contributor alias registry & handle matching
│       ├── issues/            # Issue querying and comment integration
│       ├── models.py          # Hybrid dictionary/attribute data transfer objects
│       ├── pull_request/      # PR details, reviews, and submission services
│       ├── runner.py          # Subprocess runner with injection-safe execution
│       └── validation.py      # Input validation & POSIX path guards
└── tests/                     # 146 unit & ecosystem compatibility tests
```

---

## ⚡ Makefile Reference

```bash
make install       # Install ghtoolkit in editable mode
make test          # Run all 146 unit tests with verbose output
make lint          # Run ruff check and autofix
make format        # Format codebase with ruff
make lint-check    # Verify linting and formatting standards
make ci            # Run complete local CI pipeline (lint + format + tests)
make clean         # Clean temporary build and cache artifacts
```

---

## The Idea in One Sentence

> **ghToolkit turns fragmented, brittle GitHub scripts scattered across multiple projects into a single, high-performance, zero-dependency Python facade — saving developers from constantly debugging rate limits, quoting bugs, and duplicated boilerplate.**

---

## License

MIT. Built for engineering teams that want fast, safe, and unified GitHub automation across all their tools and agents.
