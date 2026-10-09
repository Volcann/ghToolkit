from __future__ import annotations

from typing import Any

from .errors import GhResponseError


def nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be a nonempty string without NUL characters")
    return value


def positive_number(value: int, name: str = "pr_number") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def result_limit(value: int | None) -> int | None:
    if value is not None:
        positive_number(value, "limit")
    return value


def object_value(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GhResponseError(f"Expected a JSON object for {context}")
    return value


def object_list(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GhResponseError(f"Expected a JSON array of objects for {context}")
    return value
