import sys

from ghtoolkit import GitHubError, run_gh


def main() -> int:
    try:
        print(run_gh(), end="")
    except GitHubError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
