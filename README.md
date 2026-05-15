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
Opens a page at `http://localhost:8080` showing today's practice schedule and a 7-day summary. The schedule is cached in memory between Google Sheets fetches; the TTL defaults to 30 minutes and can be changed with the `CACHE_TTL_MINUTES` environment variable.

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

## Deploying to Railway

[Railway](https://railway.app) is an easy way to host the web app publicly. The repo already includes the required `Procfile` and `runtime.txt`.

### Steps

1. **Sign in** at [railway.app](https://railway.app) with your GitHub account.
2. Click **New Project** → **Deploy from GitHub repo** and select this repo.
3. Once deployed, go to **Settings → Networking → Generate Domain** to get a public URL.

Railway injects a `PORT` environment variable automatically; the app reads it at startup, so no configuration is needed.

### Local vs. Railway

| Context | How it starts | Port |
|---------|--------------|------|
| Local | `python web_app.py` | 8080 (or `--port N`) |
| Local with `$PORT` | `PORT=9000 python web_app.py` | 9000 |
| Railway | `gunicorn web_app:app` (via `Procfile`) | Railway-assigned `$PORT` |

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

The raw CSV from Google Sheets can optionally be saved to `schedule_cache.csv` for inspection. It is off by default.

```bash
# CLI
python swim_schedule.py --save-csv
python swim_schedule.py 3/25/2026 --save-csv

# Web server
SAVE_CSV=1 python web_app.py
```

This file is excluded from version control.

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
