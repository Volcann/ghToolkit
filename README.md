# ghToolkit

A Python facade over GitHub CLI for commit history, pull requests, reviews, comments,
checkout, and preserved diffs. The runtime uses the Python standard library and an
installed `gh` executable. There is no web application, database, AI pipeline, or
independent token-based HTTP client.

## Install

Use Python 3.11 or newer. Install GitHub CLI and authenticate for the repository's
host with permissions appropriate to the operations you will call.

```bash
cd ghToolkit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
gh auth login
gh auth status
python main.py
```

`main.py` prints the real output of `gh version`; no version is hardcoded.
Run `gh auth login --hostname YOUR_HOST` for a GitHub Enterprise host.
Git is additionally required for local PR checkout.

With uv:

```bash
uv sync --locked
gh auth login
uv run python main.py
uv run python -m unittest discover -s tests -v
uv run python examples/offline_demo.py
```

Custom timezones use the operating system's IANA timezone database. On systems
without it, notably some Windows installations, install `tzdata` in the same
Python environment. UTC works without an external timezone database.

## Folder structure

```text
ghToolkit/
├── examples/
│   ├── __init__.py
│   ├── branch_commits.py
│   ├── offline_demo.py
│   └── read_pr.py
├── LICENSE
├── main.py
├── Makefile
├── MANIFEST.in
├── projects.json
├── pyproject.toml
├── README.md
├── src/
│   ├── __init__.py
│   ├── api.py
│   ├── commit/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── dates.py
│   ├── diff_store.py
│   ├── errors.py
│   ├── github_client.py
│   ├── issues/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── pull_request/
│   │   ├── __init__.py
│   │   ├── reviews.py
│   │   └── service.py
│   ├── py.typed
│   ├── runner.py
│   └── validation.py
├── temp/
│   └── .gitkeep
├── TEST_RESULTS.txt
├── tests/
│   ├── __init__.py
│   ├── helpers.py
│   ├── test_api.py
│   ├── test_commits.py
│   ├── test_dates.py
│   ├── test_diffs.py
│   ├── test_pull_requests.py
│   ├── test_reviews.py
│   └── test_runner.py
└── uv.lock
```

`pyproject.toml` maps the import package `ghtoolkit` to `src/`. Install the project
before running its scripts or importing it from another project. `projects.json`
is an example of constructor settings, not an implicitly loaded configuration.

## Facade design

```text
Your application
       |
       v
  GitHubClient
       |
       +-- CommitService
       +-- PullRequestService
       +-- ReviewService
       +-- IssueService
       +-- DiffStore
               |
             GhAPI / GhRunner
               |
               gh
```

`GitHubClient` coordinates the subsystem objects. Its public methods return data,
not printed output. `GhRunner` is injectable for tests and offline use. Constructing
a client does not authenticate, make requests, create files, or run Git commands.
`client.available` checks executable availability with `shutil.which`; execution
failures are handled separately when a command is actually run.

All remote access goes through `gh`, including `gh api` REST and GraphQL requests.
This project does not silently fall back to local Git history or an independent
REST-token client. Local Git checkout happens only through the explicit checkout
method. Errors are not disguised as empty results.

## Create the client

```python
from ghtoolkit import GitHubClient

client = GitHubClient(
    "OWNER/REPO",
    timezone="Asia/Karachi",
    timeout=30.0,
    temp_dir="temp",
)
```

The default timezone is UTC. The repository can also be
`github.example.com/OWNER/REPO`. Both `gh pr` and `gh api` calls use that explicit
host, rather than accidentally mixing hosts through environment defaults.
A supplied `runner` owns its own timeout setting.

## Commits: lists contain only hash and message

```python
commits = client.get_commits(
    date="2026-10-03",
    author="alice",
    branch="main",
)

commits = client.get_user_commits_for_date("alice", "2026-10-03", branch="main")
commits = client.get_commits(branch="feature/payments", limit=20)
commits = client.get_pr_commits(123)
```

Every commit list has the same shape:

```json
[
  {
    "hash": "0123456789abcdef0123456789abcdef01234567",
    "message": "Fix payment validation\n\nPreserve the full message body."
  }
]
```

No diff, file list, or author payload is added to these summaries. SHA strings are
not shortened and multiline messages are preserved. Omitting `limit` requests all
available pages. A supplied limit is applied after local filtering.

Omitting `branch` uses GitHub's repository default branch, not a hardcoded `main`.
A branch query returns commits reachable from that branch; it is not an all-branch
repository search. The `author` filter refers to commit authorship; the `date`
filter uses `commit.committer.date`, not the author's timestamp or push time.

Separate detail and diff calls:

```python
details = client.get_commit_details("COMMIT_SHA")
associated_prs = client.get_pulls_for_commit("COMMIT_SHA")
artifact = client.get_commit_diff("COMMIT_SHA")
```

`get_commit_details` returns GitHub's commit JSON, combining the paginated `files`
arrays. It adds `filesMayBeTruncated`, conservatively true when the file count
reaches GitHub's 3,000-file cap. Use a full SHA rather than a moving branch name
when reproducibility matters.

## Pull request lists

```python
created = client.get_prs(date="2026-10-03")
merged = client.get_prs(date="2026-10-03", date_field="merged", state="merged")
updated = client.get_prs(date="2026-10-03", date_field="updated")
closed = client.get_prs(date="2026-10-03", date_field="closed", state="closed")
by_author = client.get_user_prs_for_date("alice", "2026-10-03")
open_prs = client.get_prs(state="open", limit=25)
```

The list includes `number`, `title`, `state`, `url`, `author`, `createdAt`,
`updatedAt`, `closedAt`, `mergedAt`, `isDraft`, `headRefName`, and `baseRefName`.
`author` is an object with a `login` or null when unavailable.

`state` is `OPEN`, `CLOSED`, or `MERGED`. By default, all three are returned.
For this wrapper, `state="closed"` means closed **without merging**;
`date_field="closed"` by itself can also match merged PRs because merging closes
a PR. Draft status is represented separately by `isDraft`. The returned state is
the PR's **current state**, not a reconstruction of its state on the requested day.

Lists are ordered by PR number descending and do not fetch descriptions, full
commit arrays, comments, reviews, or diffs. Discovery uses `gh pr list --json`
and, when a date is supplied, `--search`. A saturated 1,000-item CLI response falls
back to a paginated `gh api` PR listing and local filtering, rather than silently
returning an incomplete capped list. GitHub search indexing can still lag recent
changes; search results are not a historical event ledger.

## One pull request in detail

```python
metadata = client.fetch_pr_metadata(123)
details = client.get_pr_details(123)
```

`fetch_pr_metadata` returns projected `gh pr view` metadata and a paginated
GraphQL commit collection. It includes the PR body, author, branches, current
state, timestamps, head/base SHAs, merge information, additions/deletions, and
commit metadata. Each detailed commit contains `oid`, `message`,
`messageHeadline`, `messageBody`, `authoredDate`, `committedDate`, and `authors`.
Authors contain `login`, `name`, and `email`; **dates are commit-level fields**, not
invented `authors[].date` values. `authorsTruncated` signals an author connection
larger than the requested 100 authors per commit.

`get_pr_details` adds paginated changed `files`, `reviews`, and aggregated
`comments`. `filesTruncated` compares retrieved files with `changedFiles` so the
REST API's file cap is visible. No diff file is fetched or saved by either method.

PR commits are retrieved with `gh api graphql --paginate --slurp` so they are not
silently limited by the REST PR-commits endpoint's documented 250-commit maximum.
Unexpected partial GraphQL data or a changing head SHA raises `GhResponseError`.
Multiple endpoint requests are not an atomic repository snapshot.

## Dates

Accept a `datetime.date` or a strict `YYYY-MM-DD` string. Date strings such as
`today`, timestamps, and datetime objects are rejected rather than guessed.
The supported calendar range is 1970 through 2099.

The interval is local midnight **inclusive** to the next local midnight
**exclusive**, converted to UTC. For `Asia/Karachi`, `2026-10-03` means:

```text
2026-10-02T19:00:00Z <= timestamp < 2026-10-03T19:00:00Z
```

Timezone-aware boundaries also handle 23- and 25-hour daylight-saving days.
PR search uses the UTC calendar dates covering that interval, then checks the
actual returned timestamp locally. Commit API windows are padded at the lower
boundary and rechecked locally so the exact start of the day is not discarded by
an exclusive server-side `since` filter.

| Data | Timestamp used |
| --- | --- |
| Repository commits | `commit.committer.date` |
| PRs, default | `createdAt` |
| PRs with another `date_field` | `updatedAt`, `mergedAt`, or `closedAt` |
| Submitted reviews | `submitted_at` |
| Issue and inline comments | `created_at` |
| Review-summary comments | `submitted_at` |

## Raw and formatted diffs, preserved in temp

```python
pr_diff = client.get_pr_diff(123)
commit_diff = client.get_commit_diff("COMMIT_SHA")

print(pr_diff.diff_path)
print(pr_diff.markdown_path)
raw_text = pr_diff.text
formatted_markdown = pr_diff.markdown
serializable_result = pr_diff.as_dict()
```

Each call writes two files in its own unique directory:

```text
temp/
└── <host-owner-repo>-<digest>/
    ├── commit/
    │   └── <ref>-<digest>-<unique>/
    │       ├── changes.diff
    │       └── changes.md
    └── pr/
        └── <number>-<digest>-<unique>/
            ├── changes.diff
            └── changes.md
```

**Yes, formatted diffs are returned.** `changes.diff` contains the exact stdout
bytes emitted by `gh`. `changes.md` and `DiffResult.markdown` wrap the readable diff
in a fenced Markdown block with the `diff` language tag. Highlighting depends on
the Markdown renderer; this is not pre-rendered HTML or colored terminal output.

PR diffs use `gh pr diff --color never`. Commit diffs use `gh api` with
`Accept: application/vnd.github.diff`. The toolkit does not strip, reindent,
reconstruct, or normalize raw patch bytes, including tabs, spaces, CRLF, and a
missing final newline. It chooses a longer Markdown fence when the patch itself
contains backticks. A non-UTF-8 patch remains byte-exact in `.diff`; the text and
Markdown views use replacement characters for undecodable bytes. GitHub and `gh`
may impose upstream content, size, timeout, or terminal-escape sanitization
behavior; preservation here means the output actually delivered by `gh`.

Files are retained after return and after process exit. Repeated requests never
overwrite earlier artifacts. Private-repository diffs may contain sensitive code;
`temp/` is ignored by Git, files are owner-only on POSIX, and you control retention
and deletion. `make clean` deliberately does not remove saved diffs.

Compatibility functions return a plain string **and still save both files**:

```python
raw_pr_diff = client.fetch_pr_diff(123)
raw_commit_diff = client.fetch_commit_diff("COMMIT_SHA")
```

There is no AST parser, symbol extraction, patch application, or automatic
suggestion generation in this package.

## Reviews and comments

```python
reviews = client.get_pr_reviews(123)
reviews_on_day = client.get_user_reviews_for_date("alice", "2026-10-03")
reviews_on_known_prs = client.get_user_reviews_for_date(
    "alice", "2026-10-03", pr_numbers=[123, 124]
)
comments = client.fetch_pr_comments(123)
comments_on_day = client.fetch_pr_comments(123, date="2026-10-03", author="alice")
```

Review results preserve GitHub's raw review fields, including `state`, `body`,
`submitted_at`, `commit_id`, and `user`. Date-query results also include
`pr_number`. Pending reviews have no submission timestamp and do not match a
submitted-review date query.

Historical review discovery scans candidate PRs through the paginated API and
checks each review's actual `submitted_at`. It does not require a PR's latest
`updated_at` to equal the requested day, which would miss reviews on PRs updated
later. This can require many requests on large repositories. Supply `pr_numbers`
when the relevant PRs are already known. Only currently accessible, retained
GitHub data can be retrieved; deleted reviews are not reconstructed.

Comments are one list of raw objects with an added `kind` of `issue`, `inline`, or
`review`. Empty review bodies are omitted from the comment list but remain in the
review list. Inline paths, line numbers, sides, reply identifiers, and other
returned fields are preserved.

`author="@me"` resolves the authenticated login through `gh api user` before
filtering commits, PRs, reviews, or comments.

## Explicit checkout and write operations

Nothing is checked out, posted, or submitted by a read method.

```python
client.checkout_pr_branch(123, local_repo_path="/path/to/local/clone")
```

Checkout runs `gh pr checkout` in the supplied clone. It does not force checkout,
reset, stash, clean, or discard local work. Git/gh will report incompatible local
changes. You can also provide `local_repo_path` to the constructor.

```python
comment_url = client.post_pr_comment(123, "## Review summary\n\nThe change looks consistent.")
```

This posts through `gh pr comment --body-file`. The temporary comment-body file is
closed before invocation and removed afterward, including on failure. It is
separate from retained diff files.

```python
metadata = client.fetch_pr_metadata(123)
review = client.create_pull_request_review(
    123,
    commit_id=metadata["headRefOid"],
    comments=[{
        "path": "src/example.py",
        "line": 42,
        "side": "RIGHT",
        "body": "Use the corrected call:\n\n```suggestion\ncorrected_code()\n```",
    }],
    body="Review summary",
)
```

The method posts a review with `event="COMMENT"` through `gh api`, passing JSON on
stdin. A full 40-character commit SHA is required. `path`, `line`, `side`, and
`body` are validated. Multiline comments can additionally specify `start_line` and
`start_side`. Suggestion Markdown is passed unchanged, not generated or rewritten.
Use line numbers and sides from the corresponding diff. GitHub validates that
comments are applicable to the PR. Writes are never retried automatically, because
an uncertain timeout/failure does not prove GitHub rejected the write.

## Failures

| Exception | Meaning |
| --- | --- |
| `GhNotInstalledError` | The executable could not be started; check installation and PATH. |
| `GhExecutionError` | Permissions, inaccessible working directory, or another OS execution failure. |
| `GhTimeoutError` | Subprocess timeout; exposes `timeout`, `stdout`, and `stderr`. |
| `GhCommandError` | Nonzero exit; exposes `returncode`, `stderr`, and `stdout`. |
| `GhResponseError` | Invalid JSON/encoding, unexpected response shape, partial GraphQL data, or changed head during retrieval. |
| `DiffStorageError` | The diff files could not be preserved. |

All inherit `GitHubError`. Caller mistakes raise `ValueError` or `TypeError`.
Exceptions retain their original cause where applicable. Authentication,
permission, rate-limit, and network failures are not changed into an empty list.
Diagnostic stderr is available on the exception but not automatically logged.

```python
from ghtoolkit import GhCommandError, GitHubError

try:
    commits = client.get_commits(date="2026-10-03")
except GhCommandError as error:
    failure = {"returncode": error.returncode, "stderr": error.stderr}
except GitHubError as error:
    failure = {"message": str(error)}
```

The timeout applies to each `gh` process, including pagination within that process,
not to an entire facade operation containing several commands. `timeout=None`
disables it. Python's subprocess timeout does not strictly bound process creation
and does not guarantee termination of every descendant process. Captured output
and paginated results are buffered in memory; this is not an unlimited-output
streaming interface. The API itself can reject or limit very large diffs.

## Use from another project

Install this directory into the consuming project's virtual environment:

```bash
python -m pip install /absolute/path/to/ghToolkit
```

Then import `GitHubClient` from `ghtoolkit`. Existing text-diff consumers can use
`fetch_pr_diff`; consumers needing paths or Markdown can use `get_pr_diff`.
The methods use one configured repository per client. No environment-variable
configuration or working-directory repository discovery is required.

## Examples and tests

```bash
python examples/offline_demo.py
python examples/branch_commits.py OWNER/REPO --branch main --date 2026-10-03 --timezone Asia/Karachi
python examples/read_pr.py OWNER/REPO 123
python -m unittest discover -s tests -v
```

The offline demo uses explicitly synthetic fixtures and writes example diff files
without invoking `gh` or contacting GitHub. Tests use mocked GitHub responses and
real local subprocesses; the patch-preservation test also runs `git apply --check`
when Git is installed. The distribution includes the actual test run in
## Universal Ecosystem Integration (Replacing Legacy Clients)

`ghToolkit` is the unified, high-performance replacement for the disparate GitHub clients previously found across:
- **`utils/lazy-reviewer`** (`pr_reviewer/github_client.py`)
- **`workedTask`** (`status_reporter/github_client.py`)
- **`volcanai`** (`cron_job/core/` and `services/`)

### 1. Replacing `lazy-reviewer`

```python
from ghtoolkit import GitHubClient

client = GitHubClient("owner/repo", local_repo_path="/path/to/repo")

# Fetch metadata & diff directly in memory
metadata = client.fetch_pr_metadata(pr_number)
diff_text = client.fetch_pr_diff(pr_number)

# Checkout PR branch locally
client.checkout_pr_branch(pr_number)

# Post top-level comment via temporary file safely
client.post_pr_comment(pr_number, "Review comment markdown")

# Submit batch inline comments
client.create_pull_request_review(
    pr_number,
    commit_sha,
    inline_comments=[
        {"path": "src/api.py", "line": 42, "side": "RIGHT", "body": "```suggestion\nnew_code()\n```"}
    ],
    body="Summary",
    event="COMMENT",
)
```

### 2. Replacing `workedTask`

```python
from ghtoolkit import GitHubClient

client = GitHubClient("owner/repo", local_repo_path="/path/to/local/clone")
client.register_author_alias("Volcann", ["Mohsin Ali", "mohsinmuhammad823@gmail.com"])

# Commits, PRs, and reviews for a target date (with local Git acceleration)
commits = client.get_user_commits_for_date("Volcann", "2026-10-09")
prs = client.get_user_prs_for_date("Volcann", "2026-10-09")
reviews = client.get_user_reviewed_prs_for_date("Volcann", "2026-10-09")

# Fetch comments across issues, reviews, and inline threads with disk caching
comments = client.get_pr_user_comments(pr_number, "Volcann", "2026-10-09", use_cache=True)
```

### 3. Replacing `volcanai`

```python
from ghtoolkit import GitHubClient, ProgressQueue

client = GitHubClient("owner/repo")

# High-throughput contributor scanning (including foreign PR mining)
owned_prs, native_commits = client.scan_contributor_contributions(
    "Volcann", limit=5000, include_foreign=True
)

# Resumable audit queue
queue = ProgressQueue("progress.txt")
queue.save([queue.make_pr_item("owner", "repo", pr) for pr in owned_prs])
next_item = queue.pop()

# Check PR state & fetch diff/commit details
state = client.get_pr_state(pr_number)
pr_diff = client.fetch_pr_diff(pr_number)
commit_diff = client.fetch_commit_diff(commit_sha)
```

## Command and API references

- GitHub CLI PR listing and JSON fields: https://cli.github.com/manual/gh_pr_list
- GitHub CLI PR metadata: https://cli.github.com/manual/gh_pr_view
- GitHub CLI PR diff and color controls: https://cli.github.com/manual/gh_pr_diff
- GitHub CLI API pagination and stdin payloads: https://cli.github.com/manual/gh_api
- GitHub commit history, diff media types, and file limits: https://docs.github.com/en/rest/commits/commits
- Pull request endpoints and collection limits: https://docs.github.com/en/rest/pulls/pulls
- Review payloads and submission timestamps: https://docs.github.com/en/rest/pulls/reviews
- Search date qualifiers: https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests
- CLI commit field definitions: https://github.com/cli/cli/blob/trunk/api/queries_pr.go
- Python subprocess behavior: https://docs.python.org/3/library/subprocess.html
