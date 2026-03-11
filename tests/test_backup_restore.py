from pathlib import Path
import sqlite3

import app

ETALON_BACKUP_PATH = Path(__file__).parent / "fixtures" / "etalon_backup.db"


def _create_db_with_habit(db_path: Path, habit_name: str) -> None:
    db = app.JournalDB(db_path)
    ok, msg = db.add_habit(habit_name)
    assert ok, msg
    db.conn.close()


def _habit_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM habits").fetchall()
    return {str(row[0]) for row in rows}


def _snapshot(db_path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(db_path) as conn:
        habits = conn.execute(
            "SELECT id, name FROM habits ORDER BY id"
        ).fetchall()
        habit_checks = conn.execute(
            "SELECT day, habit_id, checked FROM habit_checks ORDER BY day, habit_id"
        ).fetchall()
        tasks = conn.execute(
            """
            SELECT day, task_type, title, estimated_hours, start_time, spent_hours, is_done
            FROM tasks
            ORDER BY day, id
            """
        ).fetchall()
        settings = conn.execute(
            "SELECT key, value FROM settings ORDER BY key"
        ).fetchall()
        quotes_count = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()
    return {
        "habits": [(row[0], row[1]) for row in habits],
        "habit_checks": [(row[0], row[1], row[2]) for row in habit_checks],
        "tasks": [
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6]) for row in tasks
        ],
        "settings": [(row[0], row[1]) for row in settings],
        "quotes_count": [(int(quotes_count[0]),)],
    }


def test_create_sqlite_backup_bytes_and_validate(tmp_path: Path) -> None:
    db_path = tmp_path / "journal.db"
    db = app.JournalDB(db_path)
    ok, msg = db.add_habit("Read")
    assert ok, msg

    backup_bytes = app.create_sqlite_backup_bytes(db.conn)
    backup_path = tmp_path / "backup.db"
    backup_path.write_bytes(backup_bytes)
    db.conn.close()

    valid, reason = app.validate_backup_file(backup_path)
    assert valid, reason
    assert "Read" in _habit_names(backup_path)


def test_validate_backup_file_rejects_non_sqlite(tmp_path: Path) -> None:
    invalid_path = tmp_path / "not_a_db.db"
    invalid_path.write_text("not sqlite", encoding="utf-8")

    valid, reason = app.validate_backup_file(invalid_path)
    assert not valid
    assert "valid SQLite" in reason


def test_validate_backup_file_rejects_missing_tables(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.db"
    with sqlite3.connect(broken_path) as conn:
        conn.execute("CREATE TABLE habits (id INTEGER PRIMARY KEY, name TEXT)")

    valid, reason = app.validate_backup_file(broken_path)
    assert not valid
    assert "missing required tables" in reason


def test_restore_backup_file_to_path_success(tmp_path: Path) -> None:
    target_db = tmp_path / "target.db"
    source_db = tmp_path / "source.db"

    _create_db_with_habit(target_db, "OldHabit")
    _create_db_with_habit(source_db, "NewHabit")

    ok, msg = app.restore_backup_file_to_path(source_db, target_db)

    assert ok, msg
    assert _habit_names(target_db) == {"NewHabit"}


def test_restore_backup_file_to_path_rolls_back_on_copy_failure(
    tmp_path: Path, monkeypatch
) -> None:
    target_db = tmp_path / "target.db"
    source_db = tmp_path / "source.db"

    _create_db_with_habit(target_db, "StableHabit")
    _create_db_with_habit(source_db, "IncomingHabit")

    real_copy2 = app.shutil.copy2
    call_count = {"value": 0}

    def flaky_copy2(src, dst, *args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return real_copy2(src, dst, *args, **kwargs)
        raise OSError("simulated copy failure")

    monkeypatch.setattr(app.shutil, "copy2", flaky_copy2)

    ok, msg = app.restore_backup_file_to_path(source_db, target_db)

    assert not ok
    assert "Restore failed" in msg
    assert _habit_names(target_db) == {"StableHabit"}


def test_restore_from_etalon_backup_has_expected_data(tmp_path: Path) -> None:
    target_db = tmp_path / "target.db"
    _create_db_with_habit(target_db, "WillBeReplaced")

    ok, msg = app.restore_backup_file_to_path(ETALON_BACKUP_PATH, target_db)

    assert ok, msg
    snap = _snapshot(target_db)

    assert [name for _, name in snap["habits"]] == ["Workout", "Meditate"]
    assert ("2026-03-11", 1, 1) in snap["habit_checks"]
    assert ("2026-03-11", 2, 0) in snap["habit_checks"]
    assert (
        "2026-03-11",
        "focus",
        "Ship settings backup",
        1.5,
        "09:00",
        1.25,
        1,
    ) in snap["tasks"]
    assert (
        "2026-03-11",
        "small",
        "Write restore tests",
        0.5,
        "",
        0.0,
        0,
    ) in snap["tasks"]
    assert ("day_start", "08:30") in snap["settings"]
    assert ("quote_dismissed_day", "2026-03-11") in snap["settings"]
    assert snap["quotes_count"] == [(365,)]


def test_round_trip_backup_restore_keeps_data(tmp_path: Path) -> None:
    original_db = tmp_path / "original.db"
    round_trip_db = tmp_path / "round_trip.db"
    backup_path = tmp_path / "round_trip_backup.db"

    _create_db_with_habit(original_db, "Read")
    db = app.JournalDB(original_db)
    ok, msg = db.add_habit("Code")
    assert ok, msg
    db.set_setting("day_start", "07:45")
    db.set_habit_check("2026-03-12", db.list_habits()[0].id, True)
    ok, msg = db.add_task(
        day="2026-03-12",
        task_type="main",
        title="Round-trip test",
        estimated_hours=2.0,
        start_time="10:00",
    )
    assert ok, msg
    backup_bytes = app.create_sqlite_backup_bytes(db.conn)
    db.conn.close()
    backup_path.write_bytes(backup_bytes)

    app.JournalDB(round_trip_db).conn.close()
    with sqlite3.connect(round_trip_db) as conn:
        conn.execute("DELETE FROM habits")
        conn.execute("DELETE FROM habit_checks")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM settings")
        conn.execute("DELETE FROM quotes")
        conn.commit()

    ok, msg = app.restore_backup_file_to_path(backup_path, round_trip_db)
    assert ok, msg

    assert _snapshot(round_trip_db) == _snapshot(original_db)
