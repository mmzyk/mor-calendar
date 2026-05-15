"""
Flask web app for the MOR swim schedule.
Run: python web_app.py [--port PORT]
"""
import argparse
import os
from datetime import date, timedelta
from flask import Flask, render_template
from swim_schedule import load_schedule, get_practices_for_date, TEAM_NAME, SHEET_ID

app = Flask(__name__)
_SAVE_CSV = os.environ.get("SAVE_CSV", "").lower() in ("1", "true", "yes")
_CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", 5))


@app.route("/")
def index():
    try:
        events = load_schedule(max_age_minutes=_CACHE_TTL_MINUTES, save_csv=_SAVE_CSV)
    except RuntimeError as e:
        return f"<pre>Error fetching schedule: {e}</pre>", 503

    today = date.today()
    today_events = get_practices_for_date(events, today)

    upcoming = []
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        day_events = get_practices_for_date(events, day)
        upcoming.append({"date": day, "events": day_events})

    return render_template(
        "index.html",
        team_name=TEAM_NAME,
        today=today,
        today_events=today_events,
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
