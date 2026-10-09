import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

from ghtoolkit.core.dates import DateWindow, parse_date, parse_timestamp
from ghtoolkit import GhResponseError


class DateTests(unittest.TestCase):
    def test_utc_day_is_half_open(self):
        window = DateWindow.for_date("2026-10-03")
        for timestamp in ("2026-10-03T00:00:00Z", "2026-10-03T23:59:59.999999Z"):
            self.assertTrue(window.contains(timestamp))
        for timestamp in ("2026-10-02T23:59:59Z", "2026-10-04T00:00:00Z", None):
            self.assertFalse(window.contains(timestamp))

    def test_karachi_day_crosses_two_utc_dates(self):
        window = DateWindow.for_date("2026-10-03", "Asia/Karachi")
        self.assertEqual(window.start.isoformat(), "2026-10-02T19:00:00+00:00")
        self.assertEqual(window.end.isoformat(), "2026-10-03T19:00:00+00:00")
        self.assertTrue(window.contains("2026-10-02T19:00:00Z"))
        self.assertFalse(window.contains("2026-10-03T19:00:00Z"))
        self.assertEqual(window.search("created"), "created:2026-10-02..2026-10-03")

    def test_dst_day_can_have_23_hours(self):
        window = DateWindow.for_date("2026-03-08", "America/New_York")
        self.assertEqual(window.end - window.start, timedelta(hours=23))

    def test_dst_day_can_have_25_hours(self):
        window = DateWindow.for_date("2026-11-01", "America/New_York")
        self.assertEqual(window.end - window.start, timedelta(hours=25))

    def test_single_utc_day_search(self):
        self.assertEqual(
            DateWindow.for_date("2026-10-03").search("merged"), "merged:2026-10-03"
        )

    def test_commit_window_pads_start_and_filters_later(self):
        params = DateWindow.for_date("2026-10-03").commit_parameters()
        self.assertEqual(
            params, {"since": "2026-10-02T23:59:59Z", "until": "2026-10-04T00:00:00Z"}
        )

    def test_date_object_is_supported(self):
        self.assertEqual(parse_date(date(2026, 10, 3)), date(2026, 10, 3))

    def test_invalid_date_inputs(self):
        for value in (
            "20261003",
            "2026-1-1",
            "2026-02-30",
            "2026-10-03T00:00:00Z",
            None,
            20261003,
            datetime.now(),
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_date(value)

    def test_api_date_range_is_validated(self):
        for value in ("1969-12-31", "2100-01-01"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DateWindow.for_date(value)

    def test_timezone_must_exist(self):
        with self.assertRaises(ZoneInfoNotFoundError):
            DateWindow.for_date("2026-10-03", "No/Such_Zone")

    def test_timestamp_requires_timezone(self):
        for value in ("garbage", "2026-10-03T01:00:00", None):
            with self.subTest(value=value), self.assertRaises(GhResponseError):
                parse_timestamp(value)

    def test_offset_timestamps_are_normalized(self):
        self.assertEqual(
            parse_timestamp("2026-10-03T05:00:00+05:00"),
            datetime(2026, 10, 3, tzinfo=timezone.utc),
        )
