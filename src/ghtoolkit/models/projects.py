from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProjectConfig:
    owner: str
    repo: str
    name: str = "HR-Tool"
    category: str = "Backend"
    author: str = "Volcann"
    local_path: str = ""
    enabled: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "owner": self.owner,
            "repo": self.repo,
            "author": self.author,
            "local_path": self.local_path,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        return cls(
            name=data.get("name") or data.get("project_name") or "HR-Tool",
            category=data.get("category")
            or (
                "Frontend"
                if "frontend" in (data.get("repo") or "").lower()
                else "Backend"
            ),
            owner=data.get("owner", ""),
            repo=data.get("repo", ""),
            author=data.get("author", "Volcann"),
            local_path=data.get("local_path", ""),
            enabled=data.get("enabled", True),
        )
