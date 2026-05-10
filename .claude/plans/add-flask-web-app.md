# Plan: Add Flask Web App to Swim Schedule CLI

## Context

The app currently works only as a CLI tool. The goal is to also allow it to run as a web server that serves today's practice schedule (and the 7-day summary) as a plain HTML page — while keeping the CLI fully intact. Flask was chosen as the web framework; plain HTML with no CSS framework for the page style.

---

## Files to Create or Modify

| File | Action |
|------|--------|
| `swim_schedule.py` | Modify: change `sys.exit()` to raise; add `load_schedule()` cache helper |
| `web_app.py` | Create: Flask app with `/` route |
| `templates/index.html` | Create: plain HTML schedule page |
| `requirements.txt` | Create: `flask` |
| `tests/test_swim_schedule.py` | Modify: update two error-handling tests |

---

## Step 1 — Refactor `swim_schedule.py`

### 1a. Change `fetch_sheet_as_csv` error handling

Currently the function calls `sys.exit(1)` on HTTP and network errors. This crashes the web server process. Change both `sys.exit(1)` calls to `raise RuntimeError(...)` with a descriptive message. The CLI `main()` already wraps this indirectly (it will propagate to the top and print a traceback — acceptable for the CLI edge case of network failure).

Affected lines: `swim_schedule.py:40-45` (the two `except` blocks in `fetch_sheet_as_csv`).

### 1b. Add `load_schedule()` with in-memory cache

Add a module-level cache at the top of the file:

```python
_schedule_cache: list[dict] = []
_cache_fetched_at: float = 0.0
```

Add a new function after `parse_schedule`:

```python
def load_schedule(max_age_minutes: int = 30) -> list[dict]:
    """Return cached events, re-fetching from Google Sheets if stale."""
    global _schedule_cache, _cache_fetched_at
    import time
    if _schedule_cache and (time.time() - _cache_fetched_at) < max_age_minutes * 60:
        return _schedule_cache
    rows = fetch_sheet_as_csv(SHEET_URL)
    _schedule_cache = parse_schedule(rows)
    _cache_fetched_at = time.time()
    return _schedule_cache
```

---

## Step 2 — Create `web_app.py`

```python
"""
Flask web app for the MOR swim schedule.
Run: python web_app.py [--port PORT]
"""
import argparse
from datetime import date, timedelta
from flask import Flask, render_template
from swim_schedule import load_schedule, get_practices_for_date, TEAM_NAME

app = Flask(__name__)

@app.route("/")
def index():
    try:
        events = load_schedule()
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
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port)
```

---

## Step 3 — Create `templates/index.html`

Plain HTML, no external CSS. Mirrors what the CLI prints.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ team_name }} - Practice Schedule</title>
  <style>
    body { font-family: monospace; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.2rem; }
    hr { border: none; border-top: 1px solid #ccc; }
    .no-practice { color: #888; }
    .session { margin: 0.5rem 0 0.5rem 1rem; }
  </style>
</head>
<body>
  <h1>{{ team_name }}</h1>
  <p><strong>Practice Schedule Viewer</strong></p>
  <hr>

  <h2>{{ today.strftime('%A, %B %d, %Y') }} (Today)</h2>
  {% if today_events %}
    {% for ev in today_events %}
      <div class="session">
        <div>Time: {{ ev.time }}</div>
        {% if ev.group and ev.group.lower() != 'all swimmers' %}
        <div>Group: {{ ev.group }}</div>
        {% endif %}
        {% if ev.location %}
        <div>Location: {{ ev.location }}</div>
        {% endif %}
      </div>
    {% endfor %}
  {% else %}
    <p class="no-practice">No practice scheduled for today.</p>
  {% endif %}

  <hr>
  <h2>Upcoming (next 7 days)</h2>
  <ul>
  {% for day in upcoming %}
    <li>
      {{ day.date.strftime('%a %b %d') }}:
      {% if day.events %}
        {% for ev in day.events %}{{ ev.time }}{% if ev.group and ev.group.lower() != 'all swimmers' %} [{{ ev.group }}]{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}
      {% else %}
        <span class="no-practice">No practice</span>
      {% endif %}
    </li>
  {% endfor %}
  </ul>
</body>
</html>
```

---

## Step 4 — Create `requirements.txt`

```
flask
```

---

## Step 5 — Update tests in `tests/test_swim_schedule.py`

The two tests in `TestFetchSheetAsCsv` that currently assert `SystemExit` need to assert `RuntimeError` instead:

- `test_http_error_exits` → assert `RuntimeError` (not `SystemExit`)
- `test_network_error_exits` → assert `RuntimeError` (not `SystemExit`)

---

## Verification

```bash
# 1. Install Flask
pip install flask

# 2. Run existing tests — should still pass after error-handling change
python3 -m pytest tests/ -v

# 3. Start the web server
python web_app.py --port 8080
# Open http://localhost:8080 in a browser — should show today's schedule

# 4. Verify CLI still works
python swim_schedule.py
python swim_schedule.py 3/25/2026
```
