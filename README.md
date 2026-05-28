# household-tracker

Shared todo + grocery list for everyone on your wifi. Flask + SQLite + vanilla JS. No build step.

## Setup

```bash
pip install flask
python app.py
```

That's it. The DB (`tracker.db`) is created automatically on first run.

The app binds to `0.0.0.0:5000`, so anyone on your network can access it at:

```
http://<your-machine-ip>:5000
```

Find your machine's LAN IP:

- **Windows**: `ipconfig` → look for "IPv4 Address" under your active adapter (usually `192.168.x.x`)
- **macOS/Linux**: `ifconfig` or `ip addr`

## Allowing access from other devices

If other devices on your wifi can't reach the page, your firewall is almost certainly blocking inbound port 5000. Make sure your network category is private

**Windows (PowerShell as admin):**

```powershell
New-NetFirewallRule -DisplayName "Household Tracker" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -Profile Private
```

**Linux (ufw):**

```bash
sudo ufw allow 5000/tcp
```

## How it works

- **Shared lists**: todos and groceries live in the SQLite DB; everyone sees the same data.
- **Per-device themes**: theme choice is stored in each browser's `localStorage`, so each household member can pick their own.
- **Per-device collapsed state**: which sections are collapsed is also per-device, so collapsing "Bathroom" on your phone doesn't hide it on someone else's.
- **Live-ish sync**: front-end polls every 3 seconds. Good enough for a household; if you want it instant, swap to WebSockets later.

## Sections

Both lists support sections — e.g. "Bathroom / Kitchen / Living Room" for todos, "Produce / Dairy / Pantry" for groceries.

- Click **+ section** in the panel header to create one.
- Click a section name (other than Uncategorized) to rename it inline.
- Click the **✕** next to a section name to delete it — items move to Uncategorized, they're not deleted.
- Click the **▾ / ▸** toggle to collapse/expand a section.
- New items go into whichever section is selected in the dropdown next to the add box.
- Items without an explicit section land in **Uncategorized** (a built-in section that can't be renamed or deleted).

If you're upgrading from the v1 (no-sections) version, just drop the new files in place and run `python app.py`. Your existing `tracker.db` will be migrated automatically — all existing items end up in Uncategorized, where you can move them later by editing the DB if you want (or just leave them).

## Themes

Default is the terminal green you've been using. Also includes: amber terminal, paper (clean light), rose (pink), ocean (dark blue), dracula.

To add more, just append a `[data-theme="name"]` block in `static/style.css` and add an `<option>` to the select in `templates/index.html`.

## File layout

```
household-tracker/
├── app.py              # Flask app + SQLite + REST API
├── tracker.db          # created on first run
├── templates/
│   └── index.html
└── static/
    ├── style.css       # all themes
    └── app.js          # front-end logic
```

## API (if you want to script against it)

```
GET    /api/todos
POST   /api/todos                       {"text": "...", "section_id": <optional>}
POST   /api/todos/<id>/toggle
DELETE /api/todos/<id>

GET    /api/todos/sections
POST   /api/todos/sections              {"name": "..."}
PATCH  /api/todos/sections/<id>         {"name": "..."}
DELETE /api/todos/sections/<id>         (items move to Uncategorized)

GET    /api/groceries
POST   /api/groceries                   {"text": "...", "section_id": <optional>}
POST   /api/groceries/<id>/toggle
DELETE /api/groceries/<id>

GET    /api/groceries/sections
POST   /api/groceries/sections          {"name": "..."}
PATCH  /api/groceries/sections/<id>     {"name": "..."}
DELETE /api/groceries/sections/<id>     (items move to Uncategorized)
```

## Production note

`app.run()` is fine for a household LAN. If you ever want it more robust, run it behind `waitress` (cross-platform, pip-installable):

```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 app:app
```
