# 🏊 Swim Team Practice Schedule Viewer

A simple Python app that reads the **MOR North Raleigh Swim Team** practice
schedule directly from the coaches' public Google Sheet and tells parents
exactly when practice is — today, tomorrow, or any date they choose.

---

## Requirements

- **Python 3.10+** (uses built-in libraries only — no pip installs needed)
- An internet connection (to fetch the live Google Sheet)

---

## Usage

### Interactive mode (recommended)
```bash
python swim_schedule.py
```
The app will:
1. Show today's practice time(s) instantly
2. Display a 7-day upcoming practice summary
3. Let you type any date to look up

### Look up a specific date directly
```bash
python swim_schedule.py 3/25/2026
python swim_schedule.py "March 25, 2026"
python swim_schedule.py 2026-03-25
```

---

## Date input formats accepted (interactive mode)
| You type          | Interpreted as       |
|-------------------|----------------------|
| `today`           | Today's date         |
| `tomorrow`        | Tomorrow's date      |
| `3/25`            | March 25, this year  |
| `3/25/2026`       | March 25, 2026       |
| `March 25`        | March 25, this year  |
| `March 25, 2026`  | March 25, 2026       |
| `2026-03-25`      | March 25, 2026       |

---

## How it works

The app fetches the Google Sheet as a CSV export (`/export?format=csv`), then:
- Auto-detects the header row
- Maps columns (Date, Group, Time, Location, Notes) by name — so minor
  reformatting by the coaches won't break things
- Parses dates in a variety of formats
- Filters and displays sessions for the requested day

> **No API key required.** The sheet is publicly readable, so the app uses
> the standard Google Sheets CSV export URL.

---

## Configuration

At the top of `swim_schedule.py` you can change:

```python
SHEET_ID  = "1mudmCQkme9X2MFTCLCB2_sCmyJD6z8UqvmcdGcWGY7k"   # Google Sheet ID
TEAM_NAME = "MOR North Raleigh Swim Team"                       # Displayed in header
```

---

## Sample output

```
========================================================
  🏊  MOR North Raleigh Swim Team
      Practice Schedule Viewer
========================================================

  Fetching schedule from Google Sheets…
  ✔  Loaded 42 practice session(s)
     covering Mar 01 – Apr 30, 2026

📅  Saturday, March 21, 2026 (Today)
--------------------------------------------------------
  ✔  1 practice session(s) found:

    🕐  Time     : 8:00 AM – 9:30 AM
    👥  Group    : Age Group
    📍  Location : North Raleigh Aquatic Center

────────────────────────────────────────────────────────
  📆  Upcoming practices (next 7 days):

  Sun Mar 22: No practice
  Mon Mar 23: 5:30 PM – 7:00 PM [Senior]
  ...
```
