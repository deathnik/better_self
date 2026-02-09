# Daily Journal App (Python + Flet)

Cross-platform daily journal app in Python with:
- Habits tracking (up to 5 habits)
- Daily habit checkboxes
- Week/month/year completion stats
- Daily tasks with timing, needed minutes, and editable spent minutes

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
flet build apk app.py
```

iOS:
```bash
flet build ipa app.py
```

Notes:
- iOS packaging requires macOS + Xcode.
- App data is stored in `journal.db`.
