"""
Swim Team Practice Schedule Viewer
Reads the MOR North Raleigh swim team schedule from a public Google Sheet
and tells parents what practice times are today (or any day they choose).
"""

import sys
import re
from datetime import datetime, date
import urllib.request
import csv
import io

# ── Configuration ────────────────────────────────────────────────────────────
SHEET_ID = "1mudmCQkme9X2MFTCLCB2_sCmyJD6z8UqvmcdGcWGY7k"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&id={SHEET_ID}"
TEAM_NAME = "MOR North Raleigh Swim Team"
# ─────────────────────────────────────────────────────────────────────────────


def fetch_sheet_as_csv(url: str) -> list[list[str]]:
    """Download the Google Sheet as CSV and return rows as a list of lists."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (swim-schedule-app/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
        reader = csv.reader(io.StringIO(raw))
        rows = [row for row in reader]
        return rows
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP error fetching sheet: {e.code} {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  ✗ Network error: {e.reason}")
        print("    Make sure you have an internet connection.")
        sys.exit(1)


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_schedule(rows: list[list[str]]) -> list[dict]:
    """
    Parse raw CSV rows into a list of practice event dicts:
        {date, day_of_week, group, time, location, notes}

    The sheet is expected to have a header row with columns like:
        Date | Day | Group / Team | Practice Time | Location | Notes
    We do fuzzy column detection so minor header changes don't break things.
    """
    if not rows:
        return []

    # ── Find the header row ──────────────────────────────────────────────────
    header_idx = None
    headers = []
    date_col = day_col = group_col = time_col = loc_col = notes_col = None

    for i, row in enumerate(rows):
        norm = [normalize(c) for c in row]
        # Look for a row that has both a date-like and a time-like header
        has_date = any("date" in c for c in norm)
        has_time = any("time" in c for c in norm)
        if has_date and has_time:
            header_idx = i
            headers = norm
            break

    if header_idx is None:
        # Fallback: assume first non-empty row is the header
        for i, row in enumerate(rows):
            if any(c.strip() for c in row):
                header_idx = i
                headers = [normalize(c) for c in row]
                break

    if header_idx is None:
        return []

    # ── Map column names to indices ──────────────────────────────────────────
    for idx, h in enumerate(headers):
        if "date" in h:
            date_col = idx
        elif "day" in h:
            day_col = idx
        elif "group" in h or "team" in h or "squad" in h:
            group_col = idx
        elif "time" in h:
            time_col = idx
        elif "location" in h or "pool" in h or "facility" in h or "venue" in h:
            loc_col = idx
        elif "note" in h or "comment" in h or "info" in h:
            notes_col = idx

    # Guess columns by position if detection failed
    if date_col is None:
        date_col = 0
    if time_col is None:
        time_col = min(3, len(headers) - 1)

    # ── Parse data rows ──────────────────────────────────────────────────────
    events = []
    for row in rows[header_idx + 1 :]:
        if not any(c.strip() for c in row):
            continue  # skip blank rows

        def get(col):
            if col is not None and col < len(row):
                return row[col].strip()
            return ""

        raw_date = get(date_col)
        if not raw_date:
            continue

        parsed_date = parse_date(raw_date)
        if parsed_date is None:
            continue

        events.append(
            {
                "date": parsed_date,
                "date_raw": raw_date,
                "day_of_week": get(day_col) or parsed_date.strftime("%A"),
                "group": get(group_col) or "All Swimmers",
                "time": get(time_col) or "See coach",
                "location": get(loc_col) or "",
                "notes": get(notes_col) or "",
            }
        )

    return events


def parse_date(text: str) -> date | None:
    """Try multiple date formats and return a date object or None."""
    text = text.strip()
    formats = [
        "%m/%d/%Y",  # 3/25/2026
        "%m/%d/%y",  # 3/25/26
        "%Y-%m-%d",  # 2026-03-25
        "%B %d, %Y",  # March 25, 2026
        "%b %d, %Y",  # Mar 25, 2026
        "%B %d %Y",   # March 25 2026
        "%b %d %Y",   # Mar 25 2026
        "%m-%d-%Y",   # 03-25-2026
        "%d/%m/%Y",   # 25/03/2026 (less common in US)
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def get_practices_for_date(events: list[dict], target: date) -> list[dict]:
    return [e for e in events if e["date"] == target]


def format_practice(event: dict, idx: int = 1, total: int = 1) -> str:
    """Pretty-print a single practice event."""
    lines = []
    if total > 1:
        lines.append(f"  Practice #{idx}")
    lines.append(f"    🕐  Time     : {event['time']}")
    if event["group"] and event["group"].lower() not in ("all swimmers", ""):
        lines.append(f"    👥  Group    : {event['group']}")
    if event["location"]:
        lines.append(f"    📍  Location : {event['location']}")
    if event["notes"]:
        lines.append(f"    📝  Notes    : {event['notes']}")
    return "\n".join(lines)


def print_header():
    width = 56
    print("=" * width)
    print(f"  🏊  {TEAM_NAME}")
    print(f"      Practice Schedule Viewer")
    print("=" * width)


def print_day_result(events: list[dict], target: date, label: str = ""):
    day_str = target.strftime("%A, %B %d, %Y")
    tag = f" ({label})" if label else ""
    print(f"\n📅  {day_str}{tag}")
    print("-" * 56)

    if not events:
        print("  ✖  No practice scheduled for this day.\n")
        return

    print(f"  ✔  {len(events)} practice session(s) found:\n")
    for i, ev in enumerate(events, 1):
        print(format_practice(ev, i, len(events)))
        if i < len(events):
            print()
    print()


def interactive_mode(events: list[dict]):
    """Let the user keep querying dates until they quit."""
    today = date.today()
    print_day_result(
        get_practices_for_date(events, today), today, label="Today"
    )

    # Show next 7 days summary
    print("─" * 56)
    print("  📆  Upcoming practices (next 7 days):\n")
    found_any = False
    for offset in range(1, 8):
        from datetime import timedelta
        check = today + timedelta(days=offset)
        day_events = get_practices_for_date(events, check)
        if day_events:
            found_any = True
            times = ", ".join(e["time"] for e in day_events)
            groups = ", ".join(
                e["group"] for e in day_events if e["group"] not in ("", "All Swimmers")
            )
            group_str = f" [{groups}]" if groups else ""
            print(f"  {check.strftime('%a %b %d')}: {times}{group_str}")
    if not found_any:
        print("  No upcoming practices found in the next 7 days.")
    print()

    # Interactive lookup
    print("─" * 56)
    print("  Enter a date to look up (or press Enter to quit).")
    print("  Format examples: 3/25/2026  |  March 25  |  2026-03-25")
    print()

    while True:
        try:
            user_input = input("  Date > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye! 🏊")
            break

        if not user_input:
            print("  Goodbye! 🏊")
            break

        # Allow "today" / "tomorrow" shortcuts
        if user_input.lower() == "today":
            target = today
        elif user_input.lower() == "tomorrow":
            from datetime import timedelta
            target = today + timedelta(days=1)
        else:
            # Try to fill in missing year
            if re.match(r"^\d{1,2}/\d{1,2}$", user_input):
                user_input += f"/{today.year}"
            elif re.match(r"^[A-Za-z]+ \d{1,2}$", user_input):
                user_input += f" {today.year}"

            target = parse_date(user_input)
            if target is None:
                print(f"  ⚠  Couldn't parse '{user_input}'. Try MM/DD/YYYY or 'March 25'.\n")
                continue

        print_day_result(get_practices_for_date(events, target), target)


def main():
    print_header()
    print(f"\n  Fetching schedule from Google Sheets…")

    rows = fetch_sheet_as_csv(SHEET_URL)
    events = parse_schedule(rows)

    if not events:
        print("\n  ⚠  No practice data found in the sheet.")
        print("  The sheet may be formatted differently than expected.")
        print(f"  Sheet URL: {SHEET_URL}")
        sys.exit(1)

    # Find date range
    dates = [e["date"] for e in events]
    print(f"  ✔  Loaded {len(events)} practice session(s)")
    print(f"     covering {min(dates).strftime('%b %d')} – {max(dates).strftime('%b %d, %Y')}\n")

    # If a date was passed as a CLI argument, just print that day and exit
    if len(sys.argv) > 1:
        raw_arg = " ".join(sys.argv[1:])
        target = parse_date(raw_arg)
        if target is None:
            print(f"  ⚠  Could not parse date argument: '{raw_arg}'")
            sys.exit(1)
        print_day_result(get_practices_for_date(events, target), target)
    else:
        interactive_mode(events)


if __name__ == "__main__":
    main()
