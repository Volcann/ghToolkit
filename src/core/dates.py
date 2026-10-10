from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import TypeAlias
from zoneinfo import ZoneInfo

from .errors import GhResponseError

DateInput: TypeAlias = str | date


def resolve_timezone(zone: str) -> tzinfo:
    return UTC if zone == "UTC" else ZoneInfo(zone)


def parse_date(value: DateInput) -> date:
    if isinstance(value, datetime):
        raise ValueError("Use a date or YYYY-MM-DD string, not a datetime")  # noqa: TRY004, TRY003
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must have the format YYYY-MM-DD")  # noqa: TRY003
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid calendar date") from exc  # noqa: TRY003


def parse_timestamp(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
    except (AttributeError, TypeError, ValueError) as exc:
        raise GhResponseError("Expected an ISO timestamp from GitHub") from exc  # noqa: TRY003
    if timestamp.tzinfo is None:
        raise GhResponseError("GitHub returned a timestamp without a timezone")  # noqa: TRY003
    return timestamp.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class DateWindow:
    start: datetime
    end: datetime

    @classmethod
    def for_date(cls, value: DateInput, zone: str = "UTC") -> DateWindow:
        day = parse_date(value)
        if not 1970 <= day.year <= 2099:
            raise ValueError("date must be between 1970-01-01 and 2099-12-31")  # noqa: TRY003
        tz = resolve_timezone(zone)
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
        return cls(start.astimezone(UTC), end.astimezone(UTC))

    def contains(self, timestamp: str | None) -> bool:
        return (
            timestamp is not None
            and self.start <= parse_timestamp(timestamp) < self.end
        )

    def search(self, field: str) -> str:
        first = self.start.date().isoformat()
        last = (self.end - timedelta(microseconds=1)).date().isoformat()
        return f"{field}:{first}" if first == last else f"{field}:{first}..{last}"

    def commit_parameters(self) -> dict[str, str]:
        earliest = datetime(1970, 1, 1, tzinfo=UTC)
        since = max(earliest, self.start - timedelta(seconds=1))
        return {"since": iso_utc(since), "until": iso_utc(self.end)}
