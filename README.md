# Daily Journal App (Python + Flet)

Cross-platform daily journal app in Python with:
- Habits tracking (up to 5 habits)
- Daily habit checkboxes
- Week/month/year completion stats
- Daily tasks split into groups:
  - Focus of the day (max 1)
  - Main tasks (max 2)
  - Small tasks (unlimited)
  - Pleasures (unlimited)
  - Reserved time slot (unlimited, lowest priority)
- Each task has type, name, estimated length in hours, optional start time, and editable spent hours
- Task rows include a done checkbox
- Day start setting (default `09:00`) for timeline planning
- Tasks without start time are auto-packed into first available slots by priority: focus -> main -> small -> pleasure -> reserved
- Timeline panel visualizing scheduled tasks, auto-packed tasks, done tasks, and empty timeslots

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run locally

Desktop app:
```bash
python app.py
```

Web app:
```bash
flet run --web app.py
```

## Mobile builds

Install Flet CLI tools and platform prerequisites first.

Android APK:
```bash
flet build apk .
```

This project is configured to build split APKs per ABI and exclude local
development artifacts from packaging to keep APK size down.

iOS:
```bash
flet build ipa app.py
```

Notes:
- iOS packaging requires macOS + Xcode.
- App data is stored in `journal.db`.
