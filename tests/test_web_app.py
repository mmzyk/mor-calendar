"""Tests for web_app.py"""
import os
import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo


class TestResolveDisplayDate(unittest.TestCase):

    def _call(self):
        from web_app import _resolve_display_date
        return _resolve_display_date()

    def test_uses_eastern_timezone(self):
        # 1:00 AM UTC on June 2 is 9:00 PM EDT on June 1 (UTC-4 in summer).
        # A UTC-based implementation would return June 2; Eastern must return June 1.
        eastern_dt = datetime(2026, 6, 1, 21, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        with patch.dict(os.environ, {"DISPLAY_DATE": ""}):
            with patch("web_app.datetime") as mock_dt:
                mock_dt.now.return_value = eastern_dt
                result = self._call()
        mock_dt.now.assert_called_once_with(ZoneInfo("America/New_York"))
        self.assertEqual(result, date(2026, 6, 1))

    def test_display_date_env_overrides_clock(self):
        with patch.dict(os.environ, {"DISPLAY_DATE": "2026-01-15"}):
            result = self._call()
        self.assertEqual(result, date(2026, 1, 15))

    def test_invalid_display_date_raises(self):
        with patch.dict(os.environ, {"DISPLAY_DATE": "not-a-date"}):
            with self.assertRaises(ValueError):
                self._call()


class TestParseTimeRange(unittest.TestCase):
    """swim_schedule.parse_time_range turns sheet time strings into (start, end) times."""

    def _parse(self, text):
        from swim_schedule import parse_time_range
        return parse_time_range(text)

    def test_basic_am_range(self):
        self.assertEqual(self._parse("5:00-6:30am RAV"), (time(5, 0), time(6, 30)))

    def test_basic_pm_range_with_trailing_text(self):
        self.assertEqual(self._parse("3:30-5:30pm OPT +wts"), (time(15, 30), time(17, 30)))

    def test_uppercase_meridiem(self):
        self.assertEqual(self._parse("5:00-6:30PM GWC"), (time(17, 0), time(18, 30)))

    def test_abbreviated_meridiems_hour_only(self):
        # "10a-12p RAV SAT!" style used for Saturday practices
        self.assertEqual(self._parse("10a-12p RAV SAT!"), (time(10, 0), time(12, 0)))

    def test_hour_only_single_trailing_meridiem(self):
        self.assertEqual(self._parse("1-3p GWC SAT!"), (time(13, 0), time(15, 0)))

    def test_start_meridiem_inferred_from_end(self):
        self.assertEqual(self._parse("6:45-8:30pm GWC"), (time(18, 45), time(20, 30)))

    def test_start_flips_meridiem_when_range_would_be_backwards(self):
        # 11:00pm-1:00pm is invalid, so start must be 11:00am
        self.assertEqual(self._parse("11:00-1:00pm GWC"), (time(11, 0), time(13, 0)))

    def test_range_embedded_in_longer_text(self):
        self.assertEqual(self._parse("8:00-10:00am GWC / Qualifier"), (time(8, 0), time(10, 0)))

    def test_no_time_returns_none(self):
        self.assertIsNone(self._parse("Qualifier Meet"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self._parse(""))

    def test_no_meridiem_at_all_returns_none(self):
        # Ambiguous without am/pm anywhere — caller falls back to all-day
        self.assertIsNone(self._parse("3:30-5:30 OPT"))


def _fixture_events():
    """Minimal parsed-event dicts matching parse_schedule() output shape."""
    def ev(d, group, time_str):
        return {
            "date": d,
            "date_raw": d.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
            "day_of_week": d.strftime("%A"),
            "group": group,
            "time": time_str,
            "location": "",
            "notes": "",
        }
    return [
        ev(date(2026, 6, 1), "Senior Elite", "3:30-5:30pm OPT +wts"),   # EDT (UTC-4)
        ev(date(2026, 1, 15), "AG 4", "5:00-6:30am GWC"),               # EST (UTC-5)
        ev(date(2026, 6, 2), "Senior 1", "Qualifier Meet"),             # unparseable -> all-day
    ]


class TestScheduleIcsRoute(unittest.TestCase):

    def setUp(self):
        from web_app import app
        self.client = app.test_client()

    def _get(self, path="/schedule.ics", events=None):
        if events is None:
            events = _fixture_events()
        # Pin "today" before all fixture dates so no fixture event is stale.
        with patch.dict(os.environ, {"DISPLAY_DATE": "2026-01-01"}):
            with patch("web_app.load_schedule", return_value=events):
                return self.client.get(path)

    def test_returns_valid_calendar_content_type(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/calendar", resp.content_type)
        body = resp.get_data(as_text=True)
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("END:VCALENDAR", body)

    def test_output_round_trips_through_icalendar_parser(self):
        from icalendar import Calendar
        resp = self._get()
        cal = Calendar.from_ical(resp.get_data(as_text=True))
        vevents = [c for c in cal.walk("VEVENT")]
        self.assertEqual(len(vevents), 3)

    def test_timed_event_converts_edt_to_utc(self):
        # 3:30pm Eastern on June 1 is EDT (UTC-4) -> 19:30Z
        body = self._get().get_data(as_text=True)
        self.assertIn("DTSTART:20260601T193000Z", body)
        self.assertIn("DTEND:20260601T213000Z", body)

    def test_timed_event_converts_est_to_utc(self):
        # 5:00am Eastern on Jan 15 is EST (UTC-5) -> 10:00Z
        body = self._get().get_data(as_text=True)
        self.assertIn("DTSTART:20260115T100000Z", body)
        self.assertIn("DTEND:20260115T113000Z", body)

    def test_unparseable_time_becomes_all_day_event(self):
        body = self._get().get_data(as_text=True)
        self.assertIn("DTSTART;VALUE=DATE:20260602", body)

    def test_summary_includes_group_and_time_text(self):
        body = self._get().get_data(as_text=True)
        self.assertIn("Senior Elite", body)
        self.assertIn("3:30-5:30pm OPT +wts", body)

    def test_group_filter_is_case_insensitive(self):
        body = self._get("/schedule.ics?group=senior+elite").get_data(as_text=True)
        self.assertIn("Senior Elite", body)
        self.assertNotIn("AG 4", body)
        self.assertNotIn("Senior 1", body)

    def test_unknown_group_returns_empty_calendar(self):
        resp = self._get("/schedule.ics?group=Nonexistent")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("BEGIN:VEVENT", resp.get_data(as_text=True))

    def test_uids_are_stable_across_requests(self):
        def uids(body):
            return sorted(line for line in body.splitlines() if line.startswith("UID"))
        first = uids(self._get().get_data(as_text=True))
        second = uids(self._get().get_data(as_text=True))
        self.assertEqual(len(first), 3)
        self.assertEqual(first, second)

    def test_feed_omits_events_older_than_a_week(self):
        # The sheet retains past seasons; without pruning, the feed bloats
        # past what calendar apps accept. Events > 7 days old must be dropped.
        old = {
            "date": date(2024, 1, 5),
            "date_raw": "1/5/2024",
            "day_of_week": "Friday",
            "group": "Senior Elite",
            "time": "5:00-6:30am RAV",
            "location": "",
            "notes": "",
        }
        body = self._get(events=_fixture_events() + [old]).get_data(as_text=True)
        self.assertNotIn("2024-01-05", body)
        self.assertIn("2026-06-01", body)  # current events still present

    def test_fetch_failure_returns_503(self):
        with patch("web_app.load_schedule", side_effect=RuntimeError("boom")):
            resp = self.client.get("/schedule.ics")
        self.assertEqual(resp.status_code, 503)


class TestIndexAdvertisesCalendarFeed(unittest.TestCase):
    """The home page must tell parents how to subscribe to the feed."""

    def _get_index(self):
        from web_app import app
        with patch("web_app.load_schedule", return_value=_fixture_events()):
            with patch.dict(os.environ, {"DISPLAY_DATE": "2026-06-01"}):
                return app.test_client().get("/")

    def test_index_links_to_ics_feed_with_instructions(self):
        resp = self._get_index()
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("/schedule.ics", body)
        self.assertIn("Google Calendar", body)
        self.assertIn("Apple Calendar", body)
        self.assertIn("Outlook", body)

    def test_index_offers_per_group_feed_urls(self):
        body = self._get_index().get_data(as_text=True)
        self.assertIn("group=Senior+Elite", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
