# 🏊 Swim Team Practice Schedule Viewer

A simple Python app that reads the **MOR North Raleigh Swim Team** practice
schedule directly from the coaches' public Google Sheet and tells parents
exactly when practice is — today, tomorrow, or any date they choose.

---

## Requirements

- **Python 3.10+**
- **Flask** (`pip install -r requirements.txt`)
- An internet connection (to fetch the live Google Sheet)

---

## Usage

### Web server
```bash
python web_app.py
python web_app.py --port 9000  # custom port (default: 8080)
```
Opens a page at `http://localhost:8080` showing today's practice schedule and a 7-day summary. The schedule is cached in memory for 30 minutes between Google Sheets fetches.

### Interactive CLI (recommended for date lookups)
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

The app fetches the Google Sheet as a CSV export (`/export?format=csv`), then parses its **weekly grid layout**:
- Each week block has a header row (e.g. `"April 6-12"`) followed by group rows (e.g. `"Senior Elite"`) whose columns 1–7 contain practice times for Mon–Sun
- Dates are resolved per-cell using the day-of-week label (e.g. `"Mon. 4/6"`), correctly handling sheets that span multiple years
- Cells containing `"No Practice"` or blank are skipped

> **No API key required.** The sheet is publicly readable, so the app uses
> the standard Google Sheets CSV export URL.

---

## Running the tests

The test suite uses Python's built-in `unittest` module. No internet connection required (network calls are mocked).

```bash
python3 -m pytest tests/ -v
```

Or without pytest:

```bash
python3 -m unittest discover tests
```

Tests cover date parsing, CSV row parsing, schedule filtering, output formatting, and network error handling (using mocks — no internet connection required).

---

## CSV cache

Every time a fresh fetch occurs (each CLI run, or when the web server's 30-minute in-memory cache expires), the raw CSV is saved to `schedule_cache.csv` in the working directory for inspection. This file is excluded from version control.

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
