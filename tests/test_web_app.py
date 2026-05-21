"""Tests for web_app.py"""
import os
import unittest
from datetime import date, datetime
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
