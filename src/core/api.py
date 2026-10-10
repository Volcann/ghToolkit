from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from .errors import GhResponseError
from .runner import GhRunner
from .validation import nonempty, object_list, object_value


@dataclass(frozen=True, slots=True)
class Repository:
    host: str
    owner: str
    name: str

    @classmethod
    def parse(cls, value: str) -> Repository:
        parts = nonempty(value, "repo").split("/")
        if len(parts) == 2:
            host, owner, name = "github.com", *parts
        elif len(parts) == 3:
            host, owner, name = parts
        else:
            raise ValueError("repo must be OWNER/REPO or HOST/OWNER/REPO")  # noqa: TRY003
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise ValueError("Invalid GitHub hostname")  # noqa: TRY003
        if any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."}
            for part in (owner, name)
        ):
            raise ValueError("Invalid repository owner or name")  # noqa: TRY003
        return cls(host.lower(), owner, name)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def cli_name(self) -> str:
        return f"{self.host}/{self.owner}/{self.name}"

    @property
    def api_path(self) -> str:
        return f"repos/{self.owner}/{self.name}"


class GhAPI:
    def __init__(self, repository: Repository, runner: GhRunner):
        self.repository = repository
        self.runner = runner

    def _args(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        accept: str = "application/vnd.github+json",
    ) -> list[str]:
        endpoint = (
            path.lstrip("/")
            if path.startswith("/")
            else f"{self.repository.api_path}/{path}"
        )
        if params:
            endpoint += "?" + urlencode(params)
        return [
            "api",
            endpoint,
            "--hostname",
            self.repository.host,
            "--header",
            f"Accept: {accept}",
        ]

    def get_object(self, path: str) -> dict[str, Any]:
        return object_value(
            self.runner.run_json(*self._args(path), "--method", "GET"), path
        )

    def pages(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> list[Any]:
        query: dict[str, str | int] = {"per_page": 100, **(params or {})}
        result = self.runner.run_json(
            *self._args(path, query), "--method", "GET", "--paginate", "--slurp"
        )
        if not isinstance(result, list):
            raise GhResponseError(f"Expected paginated JSON for {path}")  # noqa: TRY003
        return result

    def list(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> list[dict[str, Any]]:
        return [
            item
            for page in self.pages(path, params)
            for item in object_list(page, path)
        ]

    def diff(self, path: str) -> bytes:
        return self.runner.run_bytes(
            *self._args(path, accept="application/vnd.github.diff"), "--method", "GET"
        )

    def post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self.runner.run_json(
            *self._args(path),
            "--method",
            "POST",
            "--input",
            "-",
            input_text=json.dumps(payload, ensure_ascii=False, allow_nan=False),
        )
        return object_value(result, path)

    def graphql_pages(
        self, query: str, variables: Mapping[str, str | int]
    ) -> list[dict[str, Any]]:
        args = [
            "api",
            "graphql",
            "--hostname",
            self.repository.host,
            "--method",
            "POST",
            "--paginate",
            "--slurp",
            "--raw-field",
            f"query={query}",
        ]
        for key, value in variables.items():
            flag = "--field" if isinstance(value, int) else "--raw-field"
            args.extend([flag, f"{key}={value}"])
        pages = object_list(self.runner.run_json(*args), "GraphQL pages")
        for page in pages:
            if page.get("errors"):
                raise GhResponseError(  # noqa: TRY003
                    "GitHub GraphQL returned errors, not a complete result"
                )
        return pages
