# User Stories

## 2026-03-11
- Added developer tooling dependencies (`ruff`, `pytest`) to support linting and test workflow in this project.
- Upgraded Flet dependency to `0.82.2` to align with newer FilePicker API behavior and reduce version mismatch issues.
- Patched backup settings flow to use synchronous `FilePicker` API (`pick_files` / `save_file`) for compatibility with current Flet versions.
- Fixed FilePicker registration for newer Flet versions by attaching picker instances to `page.services` instead of `page.overlay`.
- Fixed async FilePicker integration (`await pick_files/save_file`) to match newer Flet API and prevent coroutine-path runtime errors.
- Fixed web/mobile backup export by passing SQLite backup bytes via `src_bytes` to `FilePicker.save_file`.
- Improved backup restore compatibility by reading picker file bytes (`with_data=True`) and restoring from a temporary DB file when filesystem path is unavailable.
- Moved `ruff` and `pytest` out of runtime dependencies into development-only dependencies (`[project.optional-dependencies].dev`) and added `requirements-dev.txt`.
