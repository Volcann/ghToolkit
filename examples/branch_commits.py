import argparse
import json

from ghtoolkit import GitHubClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--branch")
    parser.add_argument("--date")
    parser.add_argument("--author")
    parser.add_argument("--timezone", default="UTC")
    args = parser.parse_args()
    client = GitHubClient(args.repo, timezone=args.timezone)
    print(
        json.dumps(
            client.get_commits(branch=args.branch, date=args.date, author=args.author),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
