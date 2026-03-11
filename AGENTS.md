# AGENTS.md

## Purpose
This file defines how AI coding agents should operate in this repository.

## Precedence
- This project `AGENTS.md` overrides default agent behavior for work in this repository.
- If there is any conflict, follow these repository rules.

## Workflow
- First read related files before editing.
- Always present a short plan before any change.
- Wait for explicit user `ok` before any file edit or implementation command.
- Run `ruff check .` and `pytest` after changes.
- Log only user-experience-facing features into `UserStories.md`.

## Versioning Policy
- For new user-facing features, automatically bump the 3rd version component (patch), for example `0.1.3 -> 0.1.4`.
- Do not bump the 2nd version component (minor) unless the user explicitly requests it in this chat.
- If a change is internal-only (tooling, tests, refactor, infra) and not user-facing, do not change version by default.
- When a version is bumped, update it in `pyproject.toml` and mention it in the change summary.

## UserStories Logging Scope
- Include: new user-visible features, UX changes, behavior changes users can notice.
- Exclude: dependency updates, tooling/lint/test setup, refactors, internal cleanup, infra-only changes.

## Project Snapshot
- App type: Python + Flet daily journal app for use across Android, iOS and desktop.
- Main entrypoint: `app.py`.
- Runtime dependency: `flet` (see `requirements.txt` / `pyproject.toml`).
- Local data: `journal.db` (SQLite, local state, should not be packaged).
- Seed data: `quotes_seed.json`.

## Environment Setup
Use this sequence unless the user asks otherwise:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Commands
- Desktop run:
  ```bash
  python app.py
  ```
- Web run:
  ```bash
  flet run --web app.py
  ```

## Build Commands
- Android APK:
  ```bash
  flet build apk .
  ```
- iOS IPA (macOS/Xcode only):
  ```bash
  flet build ipa app.py
  ```

## Code Change Rules
- Keep changes targeted; avoid broad refactors unless requested.
- Preserve existing app behavior unless the task explicitly changes behavior.
- Prefer small helper functions over large in-place logic blocks.
- Keep UI labels and user-facing copy concise and consistent.
- If adding new config, prefer `pyproject.toml` over ad-hoc files when appropriate.
- Add or update tests for all non-trivial logic.
- Follow existing style before introducing new patterns.
- On each change run tests before presenting result to user.

## Data & Persistence Rules
- Do not delete or overwrite `journal.db` unless explicitly asked.
- Treat `quotes_seed.json` as source content; avoid reformatting unrelated entries.
- Ensure any schema/data migration is backward compatible with existing local DB files.

## Git Hygiene
- Do not revert user-authored changes outside the requested scope.
- Keep diffs minimal and task-focused.
- Update `README.md` if setup/run/build behavior changes.

## Agent Response Expectations
- State assumptions when requirements are ambiguous.
- Report what was changed, where, and why.
- If verification cannot be run, state that explicitly.

## Out of Scope Defaults
Unless explicitly requested:
- Do not introduce new frameworks.
- Do not add heavy dependencies.
- Do not restructure project layout.
