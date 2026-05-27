"""
Flask web app for the MOR swim schedule.
Run: python web_app.py [--port PORT]
"""
import argparse
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, render_template
from swim_schedule import load_schedule, get_practices_for_date, group_events_by_group, get_all_groups, get_groups_for_dates, TEAM_NAME, SHEET_ID

app = Flask(__name__)
_SAVE_CSV = os.environ.get("SAVE_CSV", "").lower() in ("1", "true", "yes")
_CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", 5))

def _resolve_display_date() -> date:
    """Return the date to display, from $DISPLAY_DATE if set, else today."""
    raw = os.environ.get("DISPLAY_DATE", "").strip()
    if not raw:
        return datetime.now(ZoneInfo("America/New_York")).date()
    from swim_schedule import parse_date
    parsed = parse_date(raw)
    if parsed is None:
        raise ValueError(f"DISPLAY_DATE={raw!r} could not be parsed; use YYYY-MM-DD or MM/DD/YYYY")
    return parsed


@app.route("/")
def index():
    try:
        events = load_schedule(max_age_minutes=_CACHE_TTL_MINUTES, save_csv=_SAVE_CSV)
        today = _resolve_display_date()
    except RuntimeError as e:
        return f"<pre>Error fetching schedule: {e}</pre>", 503
    except ValueError as e:
        return f"<pre>Configuration error: {e}</pre>", 500

    today_events = get_practices_for_date(events, today)
    today_grouped = group_events_by_group(today_events)

    upcoming = []
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        day_events = get_practices_for_date(events, day)
        upcoming.append({
            "date": day,
            "grouped": group_events_by_group(day_events),
        })

    week_dates = [today] + [today + timedelta(days=i) for i in range(1, 8)]
    all_groups = get_groups_for_dates(events, week_dates)

    return render_template(
        "index.html",
        team_name=TEAM_NAME,
        today=today,
        is_today=(today == datetime.now(ZoneInfo("America/New_York")).date()),
        all_groups=all_groups,
        today_grouped=today_grouped,
        upcoming=upcoming,
        sheet_url=f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        cache_ttl_minutes=_CACHE_TTL_MINUTES,
        team_website=f"https://www.gomotionapp.com/team/ncmrwa/page/home",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOR Swim Schedule web server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)), help="Port to listen on (default: 8080 or $PORT)")
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port)
