"""
Unit tests for swim_schedule.py

Run with:  python3 -m pytest tests/ -v
       or: python3 -m unittest discover tests
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from swim_schedule import (
    normalize,
    parse_date,
    parse_schedule,
    get_practices_for_date,
    format_practice,
    fetch_sheet_as_csv,
    SHEET_URL,
)


class TestNormalize(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(normalize("Date"), "date")

    def test_strips_whitespace(self):
        self.assertEqual(normalize("  date  "), "date")

    def test_collapses_internal_spaces(self):
        self.assertEqual(normalize("Practice  Time"), "practice time")

    def test_empty_string(self):
        self.assertEqual(normalize(""), "")


class TestParseDate(unittest.TestCase):
    def test_slash_with_4digit_year(self):
        self.assertEqual(parse_date("3/25/2026"), date(2026, 3, 25))

    def test_slash_with_2digit_year(self):
        self.assertEqual(parse_date("3/25/26"), date(2026, 3, 25))

    def test_iso_format(self):
        self.assertEqual(parse_date("2026-03-25"), date(2026, 3, 25))

    def test_full_month_name(self):
        self.assertEqual(parse_date("March 25, 2026"), date(2026, 3, 25))

    def test_abbreviated_month(self):
        self.assertEqual(parse_date("Mar 25, 2026"), date(2026, 3, 25))

    def test_full_month_no_comma(self):
        self.assertEqual(parse_date("March 25 2026"), date(2026, 3, 25))

    def test_abbreviated_month_no_comma(self):
        self.assertEqual(parse_date("Mar 25 2026"), date(2026, 3, 25))

    def test_dash_format(self):
        self.assertEqual(parse_date("03-25-2026"), date(2026, 3, 25))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(parse_date("  3/25/2026  "), date(2026, 3, 25))

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_date("not a date"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_date(""))

    def test_partial_date_returns_none(self):
        self.assertIsNone(parse_date("March 25"))


class TestParseSchedule(unittest.TestCase):
    def _make_rows(self, data_rows):
        """Prepend a standard header row."""
        header = ["Date", "Day", "Group", "Practice Time", "Location", "Notes"]
        return [header] + data_rows

    def test_basic_parsing(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday", "All", "6:00–7:30 AM", "Main Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 31))
        self.assertEqual(events[0]["time"], "6:00–7:30 AM")
        self.assertEqual(events[0]["location"], "Main Pool")
        self.assertEqual(events[0]["group"], "All")

    def test_multiple_events(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday",   "Junior", "6:00 AM", "Pool A", ""],
            ["4/1/2026",  "Wednesday", "Senior", "7:00 AM", "Pool B", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["group"], "Junior")
        self.assertEqual(events[1]["group"], "Senior")

    def test_blank_rows_are_skipped(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday",   "All", "6:00 AM", "Pool", ""],
            ["", "", "", "", "", ""],
            ["4/1/2026",  "Wednesday", "All", "7:00 AM", "Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(len(events), 2)

    def test_unparseable_date_rows_are_skipped(self):
        rows = self._make_rows([
            ["TBD",       "Monday",  "All", "6:00 AM", "Pool", ""],
            ["3/31/2026", "Tuesday", "All", "6:00 AM", "Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 31))

    def test_missing_date_rows_are_skipped(self):
        rows = self._make_rows([
            ["", "Monday", "All", "6:00 AM", "Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(len(events), 0)

    def test_day_of_week_falls_back_to_computed(self):
        rows = self._make_rows([
            ["3/31/2026", "", "All", "6:00 AM", "Pool", ""],
        ])
        events = parse_schedule(rows)
        # 2026-03-31 is a Tuesday
        self.assertEqual(events[0]["day_of_week"], "Tuesday")

    def test_group_falls_back_to_all_swimmers(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday", "", "6:00 AM", "Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(events[0]["group"], "All Swimmers")

    def test_time_falls_back_to_see_coach(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday", "All", "", "Pool", ""],
        ])
        events = parse_schedule(rows)
        self.assertEqual(events[0]["time"], "See coach")

    def test_notes_captured(self):
        rows = self._make_rows([
            ["3/31/2026", "Tuesday", "All", "6:00 AM", "Pool", "Bring fins"],
        ])
        events = parse_schedule(rows)
        self.assertEqual(events[0]["notes"], "Bring fins")

    def test_empty_input(self):
        self.assertEqual(parse_schedule([]), [])

    def test_header_only_returns_empty(self):
        header = ["Date", "Day", "Group", "Practice Time", "Location", "Notes"]
        self.assertEqual(parse_schedule([header]), [])

    def test_fuzzy_header_detection(self):
        # Different capitalisation / wording should still map correctly
        header = ["EVENT DATE", "Weekday", "Squad", "Start Time", "Venue", "Info"]
        rows = [header, ["3/31/2026", "Tuesday", "Junior", "6:00 AM", "Pool A", ""]]
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 31))


class TestGetPracticesForDate(unittest.TestCase):
    def setUp(self):
        self.events = [
            {"date": date(2026, 3, 31), "time": "6:00 AM",  "group": "Junior",
             "location": "Pool A", "notes": "", "day_of_week": "Tuesday",   "date_raw": "3/31/2026"},
            {"date": date(2026, 3, 31), "time": "7:30 AM",  "group": "Senior",
             "location": "Pool B", "notes": "", "day_of_week": "Tuesday",   "date_raw": "3/31/2026"},
            {"date": date(2026, 4,  1), "time": "6:00 AM",  "group": "All",
             "location": "Pool A", "notes": "", "day_of_week": "Wednesday", "date_raw": "4/1/2026"},
        ]

    def test_returns_all_sessions_for_day(self):
        result = get_practices_for_date(self.events, date(2026, 3, 31))
        self.assertEqual(len(result), 2)

    def test_returns_single_session(self):
        result = get_practices_for_date(self.events, date(2026, 4, 1))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "All")

    def test_no_match_returns_empty(self):
        result = get_practices_for_date(self.events, date(2026, 1, 1))
        self.assertEqual(result, [])


class TestFormatPractice(unittest.TestCase):
    def _event(self, **overrides):
        base = {
            "time": "6:00–7:30 AM",
            "group": "All Swimmers",
            "location": "Main Pool",
            "notes": "",
        }
        base.update(overrides)
        return base

    def test_time_always_shown(self):
        self.assertIn("6:00–7:30 AM", format_practice(self._event()))

    def test_generic_group_not_shown(self):
        self.assertNotIn("Group", format_practice(self._event(group="All Swimmers")))

    def test_named_group_shown(self):
        self.assertIn("Junior", format_practice(self._event(group="Junior")))

    def test_location_shown_when_present(self):
        self.assertIn("Main Pool", format_practice(self._event(location="Main Pool")))

    def test_location_omitted_when_empty(self):
        self.assertNotIn("Location", format_practice(self._event(location="")))

    def test_notes_shown_when_present(self):
        self.assertIn("Bring fins", format_practice(self._event(notes="Bring fins")))

    def test_notes_omitted_when_empty(self):
        self.assertNotIn("Notes", format_practice(self._event(notes="")))

    def test_practice_number_shown_for_multiple(self):
        self.assertIn("Practice #2", format_practice(self._event(), idx=2, total=3))

    def test_practice_number_omitted_for_single(self):
        self.assertNotIn("Practice #", format_practice(self._event(), idx=1, total=1))


class TestFetchSheetAsCsv(unittest.TestCase):
    def test_parses_csv_response(self):
        fake_csv = "Date,Day,Group,Practice Time,Location,Notes\n3/31/2026,Tuesday,All,6:00 AM,Pool,\n"
        mock_response = MagicMock()
        mock_response.read.return_value = fake_csv.encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            rows = fetch_sheet_as_csv(SHEET_URL)

        self.assertEqual(rows[0], ["Date", "Day", "Group", "Practice Time", "Location", "Notes"])
        self.assertEqual(rows[1][0], "3/31/2026")

    def test_http_error_exits(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            SHEET_URL, 403, "Forbidden", {}, None
        )):
            with self.assertRaises(SystemExit):
                fetch_sheet_as_csv(SHEET_URL)

    def test_network_error_exits(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
            with self.assertRaises(SystemExit):
                fetch_sheet_as_csv(SHEET_URL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
