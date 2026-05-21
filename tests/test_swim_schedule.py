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
    group_events_by_group,
    fetch_sheet_as_csv,
    SHEET_URL,
    _is_week_header,
    _parse_day_cell,
    _extract_year,
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


class TestGridHelpers(unittest.TestCase):
    """Tests for the internal grid-parsing helpers."""

    def test_is_week_header_old_format(self):
        self.assertTrue(_is_week_header(["Jan29-Feb4", "Mon. 1/29"]))

    def test_is_week_header_old_format_month_spelled_out(self):
        self.assertTrue(_is_week_header(["March4-10", "Mon. 3/4"]))

    def test_is_week_header_new_format_with_spaces(self):
        self.assertTrue(_is_week_header(["April 6-12", "Mon. 4/6"]))

    def test_is_week_header_new_format_cross_month(self):
        self.assertTrue(_is_week_header(["March 30-April5", "Mon. 3/30"]))

    def test_is_week_header_new_format_fall(self):
        self.assertTrue(_is_week_header(["Sept 29-Oct 5", "Mon. 9/29"]))

    def test_is_week_header_rejects_group_row(self):
        self.assertFalse(_is_week_header(["Senior Elite", "5:00-6:30am RAV"]))

    def test_is_week_header_rejects_blank(self):
        self.assertFalse(_is_week_header(["", "Mon. 1/29"]))

    def test_parse_day_cell_matches_title_year(self):
        # April 6, 2026 is a Monday — resolves to 2026
        self.assertEqual(_parse_day_cell("Mon. 4/6", 2026), date(2026, 4, 6))

    def test_parse_day_cell_resolves_to_prior_year(self):
        # March 25 is Monday in 2024, not 2026 — resolves to 2024
        self.assertEqual(_parse_day_cell("Mon. 3/25", 2026), date(2024, 3, 25))

    def test_parse_day_cell_no_day_label_uses_title_year(self):
        # No day abbreviation — falls back to title year
        self.assertEqual(_parse_day_cell("4/6", 2026), date(2026, 4, 6))

    def test_parse_day_cell_no_match_returns_none(self):
        self.assertIsNone(_parse_day_cell("", 2026))

    def test_extract_year_from_title_row(self):
        rows = [["March - April 2026", "", ""], ["", "", ""]]
        self.assertEqual(_extract_year(rows), 2026)

    def test_extract_year_falls_back_to_current(self):
        from datetime import date as _date
        rows = [["No year here"]]
        self.assertEqual(_extract_year(rows), _date.today().year)


class TestParseSchedule(unittest.TestCase):
    """
    The sheet uses a weekly grid layout:
      - Week header row: col0 = date range (e.g. "Mar25-31"),
                         cols 1-7 = day+date cells (e.g. "Mon. 3/25")
      - Group rows: col0 = group name, cols 1-7 = practice times for that day
    """

    def _week_block(self, week_label, days, group_rows):
        """
        Build a minimal week block.
        days: list of up to 7 "Mon. M/D" strings (Mon-Sun)
        group_rows: list of (group_name, [time_col1, ..., time_col7])
        """
        header = [week_label] + days + [""] * (7 - len(days))
        rows = [header]
        for group, times in group_rows:
            rows.append([group] + times + [""] * (7 - len(times)))
        return rows

    def test_basic_single_event(self):
        # March 25, 2026 is a Wednesday
        rows = self._week_block(
            "Mar25-31",
            ["Wed. 3/25", "Thurs. 3/26", "Fri. 3/27", "Sat. 3/28",
             "Sun. 3/29", "Mon. 3/30", "Tues. 3/31"],
            [("Senior 1", ["6:00-7:30am RAV", "", "", "", "", "", ""])],
        )
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 25))
        self.assertEqual(events[0]["group"], "Senior 1")
        self.assertEqual(events[0]["time"], "6:00-7:30am RAV")
        self.assertEqual(events[0]["day_of_week"], "Wednesday")

    def test_no_practice_cells_are_skipped(self):
        rows = self._week_block(
            "Mar25-31",
            ["Wed. 3/25", "Thurs. 3/26"],
            [("AG 2", ["No Practice", "5:30-7:00pm RAV"])],
        )
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 26))

    def test_blank_time_cells_are_skipped(self):
        rows = self._week_block(
            "Mar25-31",
            ["Wed. 3/25", "Thurs. 3/26"],
            [("Senior Elite", ["", "5:00-6:30am RAV"])],
        )
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 3, 26))

    def test_double_session_same_group_both_captured(self):
        # A blank col0 row immediately after a group row is a second session
        # for that group on the same day.
        rows = self._week_block(
            "April 6-12",
            ["Mon. 4/6"],
            [
                ("Senior Elite", ["5:00-6:30am RAV"]),
                ("",             ["3:30-5:30pm OPT"]),
            ],
        )
        events = parse_schedule(rows)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["group"] == "Senior Elite" for e in events))
        times = {e["time"] for e in events}
        self.assertIn("5:00-6:30am RAV", times)
        self.assertIn("3:30-5:30pm OPT", times)

    def test_double_session_uses_correct_group_not_prior_group(self):
        # Blank col0 row should inherit the group immediately preceding it,
        # not an earlier group from the same week block.
        rows = self._week_block(
            "April 6-12",
            ["Mon. 4/6"],
            [
                ("AG 3",         ["4:30pm GWC"]),
                ("Senior Elite", ["5:00-6:30am RAV"]),
                ("",             ["3:30-5:30pm OPT"]),
            ],
        )
        events = parse_schedule(rows)
        second_sessions = [e for e in events if e["time"] == "3:30-5:30pm OPT"]
        self.assertEqual(len(second_sessions), 1)
        self.assertEqual(second_sessions[0]["group"], "Senior Elite")

    def test_blank_col0_row_before_first_week_header_still_skipped(self):
        # A blank col0 row in the title section (before any week header) should
        # produce no events, since last_group is empty at that point.
        title_rows = [
            ["March - April 2026", ""],
            ["", "some metadata"],
        ]
        week = self._week_block(
            "April 6-12",
            ["Mon. 4/6"],
            [("Senior 1", ["6:00am RAV"])],
        )
        events = parse_schedule(title_rows + week)
        self.assertEqual(len(events), 1)

    def test_multiple_groups_same_day(self):
        rows = self._week_block(
            "Mar25-31",
            ["Mon. 3/25"],
            [
                ("Senior 1", ["6:00am RAV"]),
                ("AG 3",     ["4:30pm GWC"]),
            ],
        )
        events = parse_schedule(rows)
        self.assertEqual(len(events), 2)
        groups = {e["group"] for e in events}
        self.assertIn("Senior 1", groups)
        self.assertIn("AG 3", groups)

    def test_multiple_weeks(self):
        # Both March 25 and April 1, 2026 are Wednesdays
        week1 = self._week_block(
            "Mar25-31",
            ["Wed. 3/25"],
            [("Senior 1", ["6:00am RAV"])],
        )
        week2 = self._week_block(
            "April1-7",
            ["Wed. 4/1"],
            [("Senior 1", ["6:00am RAV"])],
        )
        events = parse_schedule(week1 + week2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["date"], date(2026, 3, 25))
        self.assertEqual(events[1]["date"], date(2026, 4, 1))

    def test_blank_rows_are_skipped(self):
        rows = self._week_block(
            "Mar25-31",
            ["Mon. 3/25", "Tues. 3/26"],
            [("Senior 1", ["6:00am RAV", "6:00am RAV"])],
        )
        rows.insert(2, ["", "", "", "", "", "", "", ""])  # inject blank row
        events = parse_schedule(rows)
        self.assertEqual(len(events), 2)

    def test_title_rows_before_first_week_header_are_skipped(self):
        title_rows = [
            ["March - April 2026", "", ""],
            ["Updated 7/30", "", ""],
            ["North Raleigh", "", ""],
        ]
        week = self._week_block(
            "Mar25-31",
            ["Mon. 3/25"],
            [("Senior 1", ["6:00am RAV"])],
        )
        events = parse_schedule(title_rows + week)
        self.assertEqual(len(events), 1)

    def test_year_from_title_is_used(self):
        # Day-of-week labels in the sheet are often stale from a prior year's
        # template; only the title year and the M/D date numbers are trusted.
        title_rows = [["March - April 2026", ""]]
        week = self._week_block(
            "Mar25-31",
            ["Wed. 3/25"],
            [("Senior 1", ["6:00am RAV"])],
        )
        events = parse_schedule(title_rows + week)
        self.assertEqual(events[0]["date"].year, 2026)

    def test_multi_year_sheet_resolves_dates_per_week(self):
        # Simulates a sheet with both 2024 and 2026 data.
        # March 25, 2024 = Monday; April 6, 2026 = Monday.
        title_rows = [["March - April 2026", ""]]
        week_2024 = self._week_block(
            "Mar25-31",
            ["Mon. 3/25"],
            [("Senior 1", ["5:00pm WV"])],
        )
        week_2026 = self._week_block(
            "April 6-12",
            ["Mon. 4/6"],
            [("Senior 1", ["5:00pm WV"])],
        )
        events = parse_schedule(title_rows + week_2024 + week_2026)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["date"], date(2024, 3, 25))
        self.assertEqual(events[1]["date"], date(2026, 4, 6))

    def test_week_header_with_spaces_is_recognized(self):
        rows = [["April 6-12", "Mon. 4/6", "Tues. 4/7"],
                ["Senior 1",   "7:30pm RAV", ""]]
        events = parse_schedule(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], date(2026, 4, 6))

    def test_empty_input(self):
        self.assertEqual(parse_schedule([]), [])

    def test_no_group_rows_returns_empty(self):
        rows = [["Mar25-31", "Mon. 3/25", "Tues. 3/26"]]
        self.assertEqual(parse_schedule(rows), [])


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


class TestGroupEventsByGroup(unittest.TestCase):
    def _ev(self, group, time):
        return {"group": group, "time": time, "location": "", "notes": "",
                "date": date(2026, 4, 6), "date_raw": "4/6/2026", "day_of_week": "Monday"}

    def test_empty_returns_empty(self):
        self.assertEqual(group_events_by_group([]), [])

    def test_single_group_single_session(self):
        events = [self._ev("Senior Elite", "5:00-6:30am")]
        result = group_events_by_group(events)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "Senior Elite")
        self.assertEqual(len(result[0]["sessions"]), 1)

    def test_single_group_two_sessions_collapsed(self):
        events = [self._ev("Senior Elite", "5:00-6:30am"),
                  self._ev("Senior Elite", "3:30-5:30pm")]
        result = group_events_by_group(events)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["group"], "Senior Elite")
        self.assertEqual(len(result[0]["sessions"]), 2)
        times = [s["time"] for s in result[0]["sessions"]]
        self.assertIn("5:00-6:30am", times)
        self.assertIn("3:30-5:30pm", times)

    def test_two_groups_returned_separately(self):
        events = [self._ev("AG 3", "4:30pm"),
                  self._ev("Senior Elite", "5:00am")]
        result = group_events_by_group(events)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["group"], "AG 3")
        self.assertEqual(result[1]["group"], "Senior Elite")

    def test_mixed_groups_preserves_order_and_collapses_correctly(self):
        events = [self._ev("AG 3", "4:30pm"),
                  self._ev("Senior Elite", "5:00am"),
                  self._ev("Senior Elite", "3:30pm")]
        result = group_events_by_group(events)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["group"], "AG 3")
        self.assertEqual(len(result[0]["sessions"]), 1)
        self.assertEqual(result[1]["group"], "Senior Elite")
        self.assertEqual(len(result[1]["sessions"]), 2)


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

    def test_http_error_raises(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            SHEET_URL, 403, "Forbidden", {}, None
        )):
            with self.assertRaises(RuntimeError):
                fetch_sheet_as_csv(SHEET_URL)

    def test_network_error_raises(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
            with self.assertRaises(RuntimeError):
                fetch_sheet_as_csv(SHEET_URL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
