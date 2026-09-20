import argparse
import json

from ghtoolkit import GitHubClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--temp-dir", default="temp")
    args = parser.parse_args()
    client = GitHubClient(args.repo, temp_dir=args.temp_dir)
    details = client.get_pr_details(args.pr_number)
    diff = client.get_pr_diff(args.pr_number)
    print(
        json.dumps(
            {
                "pull_request": details,
                "diff_path": str(diff.diff_path),
                "markdown_path": str(diff.markdown_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
