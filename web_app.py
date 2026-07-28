"""
Flask web app for the MOR swim schedule.
Run: python web_app.py [--port PORT]
"""
import argparse
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, url_for, Response
from icalendar import Calendar, Event as IcsEvent
from swim_schedule import load_schedule, get_cache_fetched_at, get_practices_for_date, group_events_by_group, get_all_groups, get_groups_for_dates, parse_time_range, TEAM_NAME, SHEET_ID

app = Flask(__name__)
_EASTERN = ZoneInfo("America/New_York")
_SAVE_CSV = os.environ.get("SAVE_CSV", "").lower() in ("1", "true", "yes")
_CACHE_TTL_MINUTES = int(os.environ.get("CACHE_TTL_MINUTES", 5))

# Toggle to show/hide the notification banner announcing new features or changes.
_SHOW_BANNER = True 
_BANNER_TEXT = "Calendar integration and a feedback form are now available."

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
        fetched_at = get_cache_fetched_at()
        cache_updated_at = datetime.fromtimestamp(fetched_at, tz=ZoneInfo("America/New_York")).strftime("%-I:%M %p ET") if fetched_at else None
        today = _resolve_display_date()
    except RuntimeError as e:
        return f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Error</title></head><body><pre>Error fetching schedule: {e}</pre></body></html>", 503
    except ValueError as e:
        return f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>Error</title></head><body><pre>Configuration error: {e}</pre></body></html>", 500

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

    # Honor the proxy's scheme (e.g. Heroku terminates TLS) so the
    # subscribe URL shown to parents is https, not http.
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    ics_url = url_for("schedule_ics", _external=True, _scheme=scheme)
    group_ics_urls = [(g, url_for("schedule_ics", group=g, _external=True, _scheme=scheme)) for g in all_groups]

    return render_template(
        "index.html",
        team_name=TEAM_NAME,
        show_banner=_SHOW_BANNER,
        banner_text=_BANNER_TEXT,
        today=today,
        is_today=(today == datetime.now(ZoneInfo("America/New_York")).date()),
        all_groups=all_groups,
        today_grouped=today_grouped,
        upcoming=upcoming,
        ics_url=ics_url,
        group_ics_urls=group_ics_urls,
        sheet_url=f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        cache_ttl_minutes=_CACHE_TTL_MINUTES,
        cache_updated_at=cache_updated_at,
        team_website=f"https://www.gomotionapp.com/team/ncmrwa/page/home",
        # URLS to other site schedules 
        raleigh_url="https://docs.google.com/document/d/1sjPtpfdev6lrt62RtWbPInfGoVob0Q4z/edit",
        riverwood_url="https://docs.google.com/spreadsheets/d/10Sx_sgIKxvQ8ULZxEqWy3xeqhc69QwOFdd_oYvF-rTc/edit",
        silverton_url="https://docs.google.com/spreadsheets/d/102A50iMHqslIHU8__UL_dhjtERMLjzeWkF0Jo1rHORc/edit",
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _build_ics(events: list[dict], group: str = "") -> bytes:
    """Build an iCalendar feed from parsed practice events.

    Times are emitted in UTC (converted from Eastern per-date, so DST is
    handled correctly). Events whose time string can't be parsed become
    all-day events rather than being dropped. When ``group`` is given, its
    name is appended to the calendar title so a single-group subscription
    is distinguishable in the user's calendar app.
    """
    calname = f"{TEAM_NAME} Practices"
    if group:
        calname += f" - {group}"

    cal = Calendar()
    cal.add("prodid", f"-//{TEAM_NAME}//swim-schedule//EN")
    cal.add("version", "2.0")
    # NAME (RFC 7986) is the standard calendar-name property preferred by
    # newer clients; X-WR-CALNAME is the legacy field older clients read.
    # Emit both to maximize the chance the name is displayed.
    cal.add("name", calname)
    cal.add("x-wr-calname", calname)
    cal.add("x-wr-timezone", "America/New_York")

    for ev in events:
        vevent = IcsEvent()
        # UID must be stable across fetches so calendar clients update
        # events in place instead of duplicating them.
        vevent.add("uid", f"{ev['date'].isoformat()}-{_slug(ev['group'])}-{_slug(ev['time'])}@mor-swim-schedule")
        vevent.add("summary", f"{ev['group']}: {ev['time']}")
        vevent.add("dtstamp", datetime.now(timezone.utc))

        parsed = parse_time_range(ev["time"])
        if parsed:
            start_t, end_t = parsed
            vevent.add("dtstart", datetime.combine(ev["date"], start_t, tzinfo=_EASTERN).astimezone(timezone.utc))
            vevent.add("dtend", datetime.combine(ev["date"], end_t, tzinfo=_EASTERN).astimezone(timezone.utc))
        else:
            vevent.add("dtstart", ev["date"])
            vevent.add("dtend", ev["date"] + timedelta(days=1))

        cal.add_component(vevent)

    return cal.to_ical()


@app.route("/schedule.ics")
def schedule_ics():
    try:
        events = load_schedule(max_age_minutes=_CACHE_TTL_MINUTES, save_csv=_SAVE_CSV)
        today = _resolve_display_date()
    except RuntimeError as e:
        return Response(f"Error fetching schedule: {e}", status=503, mimetype="text/plain")
    except ValueError as e:
        return Response(f"Configuration error: {e}", status=500, mimetype="text/plain")

    # The sheet retains past seasons; prune stale events so the feed stays
    # small enough for calendar apps (Google rejects very large feeds).
    cutoff = today - timedelta(days=7)
    events = [ev for ev in events if ev["date"] >= cutoff]

    group = request.args.get("group", "").strip()
    if group:
        events = [ev for ev in events if ev["group"].lower() == group.lower()]
        # Prefer the group's canonical casing from the sheet; fall back to
        # the query value when the group matched nothing.
        group_label = events[0]["group"] if events else group
    else:
        # Give the all-groups feed a parallel suffix so its calendar name
        # matches the style of the per-group feeds.
        group_label = "All Groups"

    return Response(
        _build_ics(events, group=group_label),
        mimetype="text/calendar",
        headers={"Content-Disposition": 'inline; filename="mor-swim-schedule.ics"'},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOR Swim Schedule web server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)), help="Port to listen on (default: 8080 or $PORT)")
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port)
