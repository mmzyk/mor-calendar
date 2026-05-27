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


CSV_CACHE_PATH = "schedule_cache.csv"

_schedule_cache: list[dict] = []
_cache_fetched_at: float = 0.0


def fetch_sheet_as_csv(url: str, save_csv: bool = False) -> list[list[str]]:
    """Download the Google Sheet as CSV and return rows as a list of lists."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (swim-schedule-app/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
        if save_csv:
            with open(CSV_CACHE_PATH, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  💾  Saved raw CSV to {CSV_CACHE_PATH}")
        reader = csv.reader(io.StringIO(raw))
        rows = [row for row in reader]
        return rows
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP error fetching sheet: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}. Make sure you have an internet connection.")


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", text.strip().lower())


# ── Grid-format sheet parsing ─────────────────────────────────────────────────
# The sheet is laid out as a weekly grid, not a flat list, and spans multiple
# years of data appended end-to-end.
#
#   Row type A — week header (two known formats):
#       old: "Jan29-Feb4"    col1: "Mon. 1/29"  col2: "Tues. 1/30"  ...
#       new: "April 6-12"   col1: "Mon. 4/6"   col2: "Tues. 4/7"   ...
#   Row type B — group row:
#       col0: "Senior Elite" col1: "5:00-6:30am RAV"  col2: ""  ...
#   Row type C — continuation / blank col0 (extra Senior Elite PM session) — skipped
#   Row type D — blank row — skipped
#
# Columns 1–7 always correspond to Mon–Sun of the current week block.
# The year for each week is resolved per-cell from the day-of-week label.

# Matches week-range labels in both formats:
#   old (no spaces):  "Jan29-Feb4", "April1-7"
#   new (with spaces): "April 6-12", "March 30-April5", "Sept 29-Oct 5"
_WEEK_RANGE_RE = re.compile(r"^[A-Za-z]+\s*\d+[-–][A-Za-z]*\s*\d+$")

# Extracts the M/D portion from day-header cells like "Mon. 1/29" or "Thurs. 2/1"
_DAY_CELL_RE = re.compile(r"\b(\d{1,2}/\d{1,2})\b")

# Matches the day-of-week abbreviation at the start of a column header cell
_DAY_ABBR_RE = re.compile(r"^(Mon|Tues|Wed|Thurs|Fri|Sat|Sun)\.?\s+", re.IGNORECASE)
_WEEKDAY_MAP = {"mon": 0, "tues": 1, "wed": 2, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}


def _extract_year(rows: list[list[str]]) -> int:
    """Scan the first few rows for a 4-digit year (e.g. from the title row)."""
    for row in rows[:4]:
        for cell in row:
            m = re.search(r"\b(20\d{2})\b", cell)
            if m:
                return int(m.group(1))
    return date.today().year


def _is_week_header(row: list[str]) -> bool:
    """Return True if col0 looks like a week-range label."""
    return bool(row) and bool(_WEEK_RANGE_RE.match(row[0].strip()))


def _parse_day_cell(cell: str, title_year: int) -> "date | None":
    """
    Parse a day-header cell like 'Mon. 4/6' into a date object.

    The day-of-week abbreviation (Mon., Tues., etc.) is used to find the
    correct year: starting from title_year and searching outward, we return
    the first year where that M/D actually falls on the labeled weekday.
    This handles sheets that span multiple years — each week block resolves
    its own year independently.
    """
    date_m = _DAY_CELL_RE.search(cell)
    if not date_m:
        return None
    month_day = date_m.group(1)

    day_m = _DAY_ABBR_RE.match(cell.strip())
    if not day_m:
        # No day label — fall back to title year
        return parse_date(f"{month_day}/{title_year}")

    expected_weekday = _WEEKDAY_MAP[day_m.group(1).lower()]
    # Search title_year first, then expand outward so the closest year wins
    candidates = [title_year]
    for delta in range(1, 4):
        candidates += [title_year - delta, title_year + delta]
    for y in candidates:
        d = parse_date(f"{month_day}/{y}")
        if d and d.weekday() == expected_weekday:
            return d
    return parse_date(f"{month_day}/{title_year}")


def parse_schedule(rows: list[list[str]]) -> list[dict]:
    """
    Parse the MOR grid-format CSV into a flat list of practice event dicts:
        {date, day_of_week, group, time, location, notes}

    The sheet uses a weekly grid layout:
    - Week header rows (col0 = date range) define the dates for cols 1-7 (Mon-Sun).
    - Group rows (col0 = group name) carry practice times in cols 1-7.
    - Cells containing "No Practice" or blank are skipped.
    """
    if not rows:
        return []

    title_year = _extract_year(rows)
    events = []
    week_dates: list["date | None"] = []  # dates for cols 1–7 of current week

    last_group = ""

    for row in rows:
        if not any(c.strip() for c in row):
            continue  # blank row

        col0 = row[0].strip()

        if _is_week_header(row):
            # Extract Mon–Sun dates from cols 1–7, resolving each cell's year
            # independently from its day-of-week label.
            week_dates = [_parse_day_cell(row[col], title_year) if col < len(row) else None for col in range(1, 8)]
            continue

        if not week_dates:
            continue  # still in title/metadata rows before first week header

        if not col0:
            if not last_group:
                continue
            group = last_group
        else:
            group = col0
            last_group = col0

        for slot, practice_date in enumerate(week_dates):
            col_idx = slot + 1
            if practice_date is None or col_idx >= len(row):
                continue
            time_val = row[col_idx].strip()
            if not time_val or time_val.lower() == "no practice":
                continue

            events.append(
                {
                    "date": practice_date,
                    "date_raw": practice_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
                    "day_of_week": practice_date.strftime("%A"),
                    "group": group,
                    "time": time_val,
                    "location": "",
                    "notes": "",
                }
            )

    return events


def load_schedule(max_age_minutes: int = 30, save_csv: bool = False) -> list[dict]:
    """Return cached events, re-fetching from Google Sheets if stale."""
    global _schedule_cache, _cache_fetched_at
    import time
    if _schedule_cache and (time.time() - _cache_fetched_at) < max_age_minutes * 60:
        return _schedule_cache
    rows = fetch_sheet_as_csv(SHEET_URL, save_csv=save_csv)
    _schedule_cache = parse_schedule(rows)
    _cache_fetched_at = time.time()
    return _schedule_cache


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


def group_events_by_group(events: list[dict]) -> list[dict]:
    """Collapse multi-session events so each group appears once with all its sessions."""
    groups = []
    seen: dict[str, dict] = {}
    for ev in events:
        key = ev["group"]
        if key not in seen:
            entry = {"group": key, "sessions": []}
            seen[key] = entry
            groups.append(entry)
        seen[key]["sessions"].append(ev)
    return groups


def _is_named_group(group: str) -> bool:
    return bool(group) and group.lower() != "all swimmers"


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
    for g in group_events_by_group(events):
        if _is_named_group(g["group"]):
            print(f"    👥  Group    : {g['group']}")
        for ev in g["sessions"]:
            print(f"    🕐  Time     : {ev['time']}")
            if ev["location"]:
                print(f"    📍  Location : {ev['location']}")
            if ev["notes"]:
                print(f"    📝  Notes    : {ev['notes']}")
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
            print(f"  {check.strftime('%a %b %d')}:")
            for g in group_events_by_group(day_events):
                times = ", ".join(s["time"] for s in g["sessions"])
                if _is_named_group(g["group"]):
                    print(f"    {g['group']}: {times}")
                else:
                    print(f"    {times}")
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
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="MOR Swim Schedule viewer")
    parser.add_argument("date", nargs="?", help="Date to look up (e.g. 3/25/2026)")
    parser.add_argument("--save-csv", action="store_true", help="Save raw CSV to schedule_cache.csv after fetching")
    args = parser.parse_args()

    print_header()
    print(f"\n  Fetching schedule from Google Sheets…")

    try:
        rows = fetch_sheet_as_csv(SHEET_URL, save_csv=args.save_csv)
    except RuntimeError as e:
        print(f"  ✗ {e}")
        sys.exit(1)
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

    if args.date:
        target = parse_date(args.date)
        if target is None:
            print(f"  ⚠  Could not parse date argument: '{args.date}'")
            sys.exit(1)
        print_day_result(get_practices_for_date(events, target), target)
    else:
        interactive_mode(events)


if __name__ == "__main__":
    main()
