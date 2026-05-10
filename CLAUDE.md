# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run the app interactively:
```bash
python swim_schedule.py
```

Look up a specific date:
```bash
python swim_schedule.py 3/25/2026
```

Run tests:
```bash
python3 -m pytest tests/ -v
# or without pytest:
python3 -m unittest discover tests
```

Run a single test class or method:
```bash
python3 -m pytest tests/test_swim_schedule.py::TestParseSchedule -v
python3 -m pytest tests/test_swim_schedule.py::TestParseSchedule::test_basic_single_event -v
```

No dependencies beyond Python 3.10+ stdlib — no pip installs needed.

## Architecture

All logic lives in a single file: `swim_schedule.py`. The app fetches a public Google Sheet as CSV and parses it to display swim practice schedules.

### Data flow

1. `fetch_sheet_as_csv()` — downloads the Google Sheet via CSV export URL, saves a local cache to `schedule_cache.csv`, returns raw rows as `list[list[str]]`
2. `parse_schedule()` — converts the grid-format CSV into flat event dicts with keys: `date`, `date_raw`, `day_of_week`, `group`, `time`, `location`, `notes`
3. `get_practices_for_date()` — filters events by date
4. `format_practice()` / `print_day_result()` — display formatting

### Sheet format (critical to understand)

The Google Sheet uses a **weekly grid layout**, not a flat table. The parser handles this with row-type detection:

- **Week header rows** (col0 matches `_WEEK_RANGE_RE`): e.g. `"April 6-12"` or `"Jan29-Feb4"`. Cols 1–7 contain day+date cells like `"Mon. 4/6"`.
- **Group rows** (col0 = group name like `"Senior Elite"`): cols 1–7 contain practice times for Mon–Sun of the current week block.
- **Continuation rows** (col0 empty): skipped — these are extra sessions for the same group.
- **Blank rows**: skipped.

### Year resolution

The sheet spans multiple years. `_parse_day_cell()` resolves the correct year for each cell by matching the day-of-week abbreviation (e.g. `Mon.`) against the M/D date — it searches `title_year` first, then expands outward up to ±3 years to find the year where that date actually falls on the labeled weekday.

`_extract_year()` finds the title year from the first few rows (looks for a 4-digit year like `"March - April 2026"`).

### Configuration

At the top of `swim_schedule.py`:
```python
SHEET_ID  = "1mudmCQkme9X2MFTCLCB2_sCmyJD6z8UqvmcdGcWGY7k"
TEAM_NAME = "MOR North Raleigh Swim Team"
```

### Tests

Tests use `unittest` (stdlib) with `unittest.mock` for network calls — no internet connection required. The `TestParseSchedule._week_block()` helper builds minimal grid-format CSV fixtures for testing the parser.
