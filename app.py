import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
from pathlib import Path

import flet as ft

DB_PATH = Path(__file__).with_name("journal.db")
QUOTES_SEED_PATH = Path(__file__).with_name("quotes_seed.json")

TASK_TYPE_LABELS = {
    "focus": "Focus of the day",
    "main": "Main tasks",
    "small": "Small tasks",
    "pleasure": "Pleasures",
    "reserved": "Reserved time slot",
}

TASK_TYPE_ORDER = ["focus", "main", "small", "pleasure", "reserved"]

TASK_TYPE_LIMITS = {
    "focus": 1,
    "main": 2,
    "small": None,
    "pleasure": None,
    "reserved": None,
}

TASK_TYPE_COLORS = {
    "focus": ft.Colors.AMBER_200,
    "main": ft.Colors.BLUE_200,
    "small": ft.Colors.GREEN_200,
    "pleasure": ft.Colors.PINK_200,
    "reserved": ft.Colors.YELLOW_200,
}

DEFAULT_DAILY_QUOTE = ("Keep going.", "Unknown")


@lru_cache(maxsize=1)
def load_daily_quotes_from_seed(total_days: int = 365) -> list[tuple[str, str]]:
    try:
        raw = json.loads(QUOTES_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [DEFAULT_DAILY_QUOTE] * total_days

    if not isinstance(raw, list):
        return [DEFAULT_DAILY_QUOTE] * total_days

    by_day: dict[int, tuple[str, str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        day = item.get("day_of_year")
        quote = item.get("quote")
        author = item.get("author")
        if not isinstance(day, int) or day < 1 or day > total_days:
            continue
        if not isinstance(quote, str) or not quote.strip():
            continue
        if not isinstance(author, str) or not author.strip():
            continue
        by_day[day] = (quote.strip(), author.strip())

    return [by_day.get(day, DEFAULT_DAILY_QUOTE) for day in range(1, total_days + 1)]


@dataclass
class Habit:
    id: int
    name: str


@dataclass
class Task:
    id: int
    day: str
    task_type: str
    title: str
    estimated_hours: float
    start_time: str
    spent_hours: float
    is_done: bool


class JournalDB:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _column_names(self, table_name: str) -> set[str]:
        rows = self.conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS habit_checks (
                day TEXT NOT NULL,
                habit_id INTEGER NOT NULL,
                checked INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, habit_id),
                FOREIGN KEY (habit_id) REFERENCES habits(id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'small',
                title TEXT NOT NULL,
                estimated_hours REAL NOT NULL DEFAULT 0,
                start_time TEXT NOT NULL DEFAULT '',
                spent_hours REAL NOT NULL DEFAULT 0,
                is_done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                day_of_year INTEGER PRIMARY KEY,
                quote TEXT NOT NULL,
                author TEXT NOT NULL
            )
            """
        )

        columns = self._column_names("tasks")
        if "task_type" not in columns:
            self.conn.execute(
                "ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'small'"
            )
        if "estimated_hours" not in columns:
            self.conn.execute(
                "ALTER TABLE tasks ADD COLUMN estimated_hours REAL NOT NULL DEFAULT 0"
            )
        if "start_time" not in columns:
            self.conn.execute(
                "ALTER TABLE tasks ADD COLUMN start_time TEXT NOT NULL DEFAULT ''"
            )
        if "spent_hours" not in columns:
            self.conn.execute(
                "ALTER TABLE tasks ADD COLUMN spent_hours REAL NOT NULL DEFAULT 0"
            )
        if "is_done" not in columns:
            self.conn.execute(
                "ALTER TABLE tasks ADD COLUMN is_done INTEGER NOT NULL DEFAULT 0"
            )

        migrated_columns = self._column_names("tasks")
        if "planned_minutes" in migrated_columns:
            self.conn.execute(
                """
                UPDATE tasks
                SET estimated_hours = planned_minutes / 60.0
                WHERE estimated_hours = 0 AND planned_minutes > 0
                """
            )
        if "spent_minutes" in migrated_columns:
            self.conn.execute(
                """
                UPDATE tasks
                SET spent_hours = spent_minutes / 60.0
                WHERE spent_hours = 0 AND spent_minutes > 0
                """
            )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES ('day_start', '09:00')
            """
        )
        self._seed_daily_quotes()

        self.conn.commit()

    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, default),
            )
            self.conn.commit()
            return default
        return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def _seed_daily_quotes(self) -> None:
        existing = self.conn.execute("SELECT COUNT(*) AS c FROM quotes").fetchone()
        quote_count = int(existing["c"]) if existing is not None else 0
        if quote_count == 365:
            return

        daily_quotes = load_daily_quotes_from_seed(365)
        self.conn.execute("DELETE FROM quotes")
        self.conn.executemany(
            """
            INSERT INTO quotes(day_of_year, quote, author)
            VALUES (?, ?, ?)
            """,
            [(idx, quote, author) for idx, (quote, author) in enumerate(daily_quotes, start=1)],
        )

    def get_quote_for_date(self, d: date) -> tuple[str, str]:
        day_of_year = min(d.timetuple().tm_yday, 365)
        row = self.conn.execute(
            """
            SELECT quote, author
            FROM quotes
            WHERE day_of_year = ?
            """,
            (day_of_year,),
        ).fetchone()
        if row is None:
            fallback_quote, fallback_author = load_daily_quotes_from_seed(365)[
                day_of_year - 1
            ]
            return fallback_quote, fallback_author
        return str(row["quote"]), str(row["author"])

    def list_habits(self) -> list[Habit]:
        rows = self.conn.execute("SELECT id, name FROM habits ORDER BY id").fetchall()
        return [Habit(id=row["id"], name=row["name"]) for row in rows]

    def add_habit(self, name: str) -> tuple[bool, str]:
        clean = name.strip()
        if not clean:
            return False, "Habit name is required."
        current = self.conn.execute("SELECT COUNT(*) AS c FROM habits").fetchone()["c"]
        if current >= 5:
            return False, "Only up to 5 habits are allowed."
        try:
            self.conn.execute("INSERT INTO habits(name) VALUES (?)", (clean,))
            self.conn.commit()
            return True, "Habit added."
        except sqlite3.IntegrityError:
            return False, "Habit already exists."

    def get_checked_habits(self, day: str) -> set[int]:
        rows = self.conn.execute(
            "SELECT habit_id FROM habit_checks WHERE day = ? AND checked = 1", (day,)
        ).fetchall()
        return {int(row["habit_id"]) for row in rows}

    def set_habit_check(self, day: str, habit_id: int, checked: bool) -> None:
        self.conn.execute(
            """
            INSERT INTO habit_checks(day, habit_id, checked)
            VALUES (?, ?, ?)
            ON CONFLICT(day, habit_id) DO UPDATE SET checked = excluded.checked
            """,
            (day, habit_id, int(checked)),
        )
        self.conn.commit()

    def count_checked_between(self, start_day: str, end_day: str) -> int:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(checked), 0) AS total
            FROM habit_checks
            WHERE day >= ? AND day <= ?
            """,
            (start_day, end_day),
        ).fetchone()
        return int(row["total"])

    def _validate_task_type_limit(
        self, day: str, task_type: str, exclude_task_id: int | None = None
    ) -> tuple[bool, str]:
        limit = TASK_TYPE_LIMITS.get(task_type)
        if limit is None:
            return True, ""

        if exclude_task_id is None:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM tasks WHERE day = ? AND task_type = ?",
                (day, task_type),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM tasks
                WHERE day = ? AND task_type = ? AND id != ?
                """,
                (day, task_type, exclude_task_id),
            ).fetchone()

        count = int(row["c"])
        if count >= limit:
            return False, f"{TASK_TYPE_LABELS[task_type]} supports max {limit} task(s)."
        return True, ""

    def add_task(
        self,
        day: str,
        task_type: str,
        title: str,
        estimated_hours: float,
        start_time: str,
    ) -> tuple[bool, str]:
        clean_title = title.strip()
        clean_type = task_type.strip().lower()
        clean_start = start_time.strip()

        if clean_type not in TASK_TYPE_LABELS:
            return False, "Invalid task type."
        if not clean_title:
            return False, "Task name is required."
        if estimated_hours < 0:
            return False, "Estimated length cannot be negative."

        ok, msg = self._validate_task_type_limit(day, clean_type)
        if not ok:
            return False, msg

        self.conn.execute(
            """
            INSERT INTO tasks(day, task_type, title, estimated_hours, start_time, spent_hours)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (day, clean_type, clean_title, estimated_hours, clean_start),
        )
        self.conn.commit()
        return True, "Task added."

    def list_tasks(self, day: str) -> list[Task]:
        rows = self.conn.execute(
            """
            SELECT id, day, task_type, title, estimated_hours, start_time, spent_hours, is_done
            FROM tasks
            WHERE day = ?
            ORDER BY
                CASE task_type
                    WHEN 'focus' THEN 0
                    WHEN 'main' THEN 1
                    WHEN 'small' THEN 2
                    WHEN 'pleasure' THEN 3
                    WHEN 'reserved' THEN 4
                    ELSE 9
                END,
                COALESCE(NULLIF(start_time, ''), '99:99'),
                id
            """,
            (day,),
        ).fetchall()
        return [
            Task(
                id=row["id"],
                day=row["day"],
                task_type=row["task_type"] if row["task_type"] in TASK_TYPE_LABELS else "small",
                title=row["title"],
                estimated_hours=float(row["estimated_hours"] or 0),
                start_time=row["start_time"] or "",
                spent_hours=float(row["spent_hours"] or 0),
                is_done=bool(row["is_done"]),
            )
            for row in rows
        ]

    def update_task(
        self,
        task_id: int,
        day: str,
        task_type: str,
        title: str,
        estimated_hours: float,
        start_time: str,
        spent_hours: float,
        is_done: bool,
    ) -> tuple[bool, str]:
        clean_title = title.strip()
        clean_type = task_type.strip().lower()
        clean_start = start_time.strip()

        if clean_type not in TASK_TYPE_LABELS:
            return False, "Invalid task type."
        if not clean_title:
            return False, "Task name is required."
        if estimated_hours < 0 or spent_hours < 0:
            return False, "Hours cannot be negative."

        ok, msg = self._validate_task_type_limit(day, clean_type, exclude_task_id=task_id)
        if not ok:
            return False, msg

        self.conn.execute(
            """
            UPDATE tasks
            SET task_type = ?, title = ?, estimated_hours = ?, start_time = ?, spent_hours = ?, is_done = ?
            WHERE id = ?
            """,
            (
                clean_type,
                clean_title,
                estimated_hours,
                clean_start,
                spent_hours,
                int(is_done),
                task_id,
            ),
        )
        self.conn.commit()
        return True, "Task saved."

    def delete_task(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()


def parse_hours(value: str) -> float:
    raw = value.strip()
    if not raw:
        return 0.0
    return float(raw)


def parse_hhmm_to_minutes(value: str) -> int:
    clean = value.strip()
    if not clean:
        raise ValueError("empty")
    parts = clean.split(":")
    if len(parts) != 2:
        raise ValueError("invalid")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid")
    return (hour * 60) + minute


def minutes_to_hhmm(minutes: int) -> str:
    clipped = max(0, min(24 * 60, minutes))
    hour = clipped // 60
    minute = clipped % 60
    if clipped == 24 * 60:
        return "24:00"
    return f"{hour:02d}:{minute:02d}"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def year_start(d: date) -> date:
    return d.replace(month=1, day=1)


def format_ratio(done: int, possible: int) -> str:
    if possible <= 0:
        return "0/0 (0%)"
    pct = (done / possible) * 100
    return f"{done}/{possible} ({pct:.1f}%)"


def format_limit_count(task_type: str, count: int) -> str:
    limit = TASK_TYPE_LIMITS[task_type]
    if limit is None:
        return f"{count}"
    return f"{count}/{limit}"


def main(page: ft.Page) -> None:
    db = JournalDB(DB_PATH)
    current_day = date.today()

    page.title = "Daily Journal"
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 1100
    page.window_height = 860
    page.scroll = ft.ScrollMode.AUTO

    date_label = ft.Text(size=22, weight=ft.FontWeight.BOLD)
    status_text = ft.Text(color=ft.Colors.BLUE_GREY_700)

    habit_column = ft.Column(spacing=8)
    task_list_column = ft.Column(spacing=8)
    timeline_column = ft.Column(spacing=8)

    week_stat = ft.Text()
    month_stat = ft.Text()
    year_stat = ft.Text()

    add_habit_input = ft.TextField(label="New habit", expand=True)

    add_task_type = ft.Dropdown(
        label="Type",
        value="small",
        width=210,
        options=[
            ft.dropdown.Option(key=k, text=TASK_TYPE_LABELS[k]) for k in TASK_TYPE_ORDER
        ],
    )
    task_title_input = ft.TextField(label="Task name", width=320, autofocus=True)
    task_estimated_input = ft.TextField(label="Estimated length (h)", width=190)
    task_time_input = ft.TextField(label="Start time (HH:MM)", width=170)
    day_start_input = ft.TextField(
        label="Day start",
        width=130,
        value=db.get_setting("day_start", "09:00"),
    )
    task_form_status = ft.Text(color=ft.Colors.BLUE_GREY_700, size=12)
    task_edit_dialog: ft.AlertDialog | None = None

    def selected_day_str() -> str:
        return current_day.isoformat()

    def show_message(message: str, ok: bool = True) -> None:
        status_text.value = message
        status_text.color = ft.Colors.GREEN_700 if ok else ft.Colors.RED_700

    def show_task_form_message(message: str, ok: bool = True) -> None:
        task_form_status.value = message
        task_form_status.color = ft.Colors.GREEN_700 if ok else ft.Colors.RED_700

    def validate_time_or_empty(value: str) -> bool:
        clean = value.strip()
        if not clean:
            return True
        try:
            parse_hhmm_to_minutes(clean)
            return True
        except ValueError:
            return False

    def refresh_stats() -> None:
        habits = db.list_habits()
        habit_count = len(habits)

        def period_stat(start: date, end: date) -> str:
            days = (end - start).days + 1
            possible = habit_count * days
            done = db.count_checked_between(start.isoformat(), end.isoformat())
            return format_ratio(done, possible)

        week_stat.value = f"Week:  {period_stat(week_start(current_day), current_day)}"
        month_stat.value = f"Month: {period_stat(month_start(current_day), current_day)}"
        year_stat.value = f"Year:  {period_stat(year_start(current_day), current_day)}"

    def refresh_habits() -> None:
        habits = db.list_habits()
        checked = db.get_checked_habits(selected_day_str())
        habit_column.controls.clear()

        for habit in habits:
            cb = ft.Checkbox(label=habit.name, value=habit.id in checked)

            def on_change(e: ft.ControlEvent, hid: int = habit.id) -> None:
                db.set_habit_check(selected_day_str(), hid, bool(e.control.value))
                refresh_stats()
                page.update()

            cb.on_change = on_change
            habit_column.controls.append(cb)

        if not habits:
            habit_column.controls.append(ft.Text("No habits yet. Add up to 5 habits."))

        add_habit_input.disabled = len(habits) >= 5

    def get_day_start_minutes() -> int:
        value = day_start_input.value.strip()
        if not value:
            return parse_hhmm_to_minutes("09:00")
        return parse_hhmm_to_minutes(value)

    def refresh_timeline(tasks: list[Task]) -> None:
        timeline_column.controls.clear()
        day_end = 24 * 60
        try:
            day_start_minutes = get_day_start_minutes()
        except ValueError:
            day_start_minutes = parse_hhmm_to_minutes("09:00")

        fixed_intervals: list[tuple[int, int, Task, bool]] = []
        unscheduled: list[Task] = []

        for t in tasks:
            if t.estimated_hours <= 0:
                unscheduled.append(t)
                continue
            if not t.start_time:
                unscheduled.append(t)
                continue
            try:
                start = parse_hhmm_to_minutes(t.start_time)
            except ValueError:
                unscheduled.append(t)
                continue
            end = min(day_end, start + int(round(t.estimated_hours * 60)))
            if end <= start:
                unscheduled.append(t)
                continue
            fixed_intervals.append((start, end, t, False))

        fixed_intervals.sort(key=lambda i: i[0])
        occupied: list[tuple[int, int]] = [(s, e) for s, e, _, _ in fixed_intervals]

        def find_first_slot(duration_minutes: int) -> int | None:
            if duration_minutes <= 0:
                return None
            cursor = day_start_minutes
            for start_m, end_m in sorted(occupied, key=lambda x: x[0]):
                if end_m <= cursor:
                    continue
                if start_m > cursor and (start_m - cursor) >= duration_minutes:
                    return cursor
                cursor = max(cursor, end_m)
            if (day_end - cursor) >= duration_minutes:
                return cursor
            return None

        packed_intervals: list[tuple[int, int, Task, bool]] = []
        unscheduled_sorted = sorted(
            unscheduled,
            key=lambda t: (
                TASK_TYPE_ORDER.index(t.task_type)
                if t.task_type in TASK_TYPE_ORDER
                else len(TASK_TYPE_ORDER),
                t.id,
            ),
        )
        not_placed_count = 0
        for t in unscheduled_sorted:
            duration = int(round(t.estimated_hours * 60))
            slot = find_first_slot(duration)
            if slot is None:
                not_placed_count += 1
                continue
            end = min(day_end, slot + duration)
            packed_intervals.append((slot, end, t, True))
            occupied.append((slot, end))

        intervals = sorted(fixed_intervals + packed_intervals, key=lambda i: i[0])

        def add_empty_block(start_m: int, end_m: int) -> None:
            if end_m <= start_m:
                return
            timeline_column.controls.append(
                ft.Container(
                    content=ft.Text(
                        f"Empty: {minutes_to_hhmm(start_m)} - {minutes_to_hhmm(end_m)}"
                    ),
                    padding=10,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_100,
                )
            )

        def add_task_block(start_m: int, end_m: int, t: Task, packed: bool) -> None:
            title_prefix = "[DONE] " if t.is_done else ""
            time_suffix = " (auto)" if packed else ""
            timeline_column.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                TASK_TYPE_LABELS.get(t.task_type, "Task"),
                                size=12,
                                color=ft.Colors.BLUE_GREY_800,
                            ),
                            ft.Text(f"{title_prefix}{t.title}", weight=ft.FontWeight.BOLD),
                            ft.Text(
                                f"{minutes_to_hhmm(start_m)} - {minutes_to_hhmm(end_m)}{time_suffix}"
                            ),
                        ],
                        spacing=2,
                    ),
                    padding=10,
                    border=ft.border.all(
                        1, ft.Colors.GREY_500 if t.is_done else ft.Colors.BLUE_GREY_300
                    ),
                    border_radius=8,
                    bgcolor=(
                        ft.Colors.GREY_300
                        if t.is_done
                        else TASK_TYPE_COLORS.get(t.task_type, ft.Colors.BLUE_100)
                    ),
                )
            )

        if not intervals:
            add_empty_block(day_start_minutes, day_end)
        else:
            cursor = day_start_minutes
            for start_m, end_m, task, packed in intervals:
                if end_m <= day_start_minutes:
                    continue
                if start_m < day_start_minutes:
                    start_m = day_start_minutes
                if start_m > cursor:
                    add_empty_block(cursor, start_m)
                if start_m < cursor:
                    timeline_column.controls.append(
                        ft.Text(
                            f"Overlap detected near {minutes_to_hhmm(start_m)}",
                            color=ft.Colors.RED_700,
                        )
                    )
                add_task_block(start_m, end_m, task, packed)
                cursor = max(cursor, end_m)
            if cursor < day_end:
                add_empty_block(cursor, day_end)

        if not_placed_count > 0:
            timeline_column.controls.append(
                ft.Text(
                    f"{not_placed_count} task(s) could not be placed on timeline.",
                    color=ft.Colors.BLUE_GREY_700,
                )
            )

    def refresh_tasks() -> None:
        tasks = db.list_tasks(selected_day_str())
        tasks_by_type: dict[str, list[Task]] = {k: [] for k in TASK_TYPE_ORDER}

        for t in tasks:
            bucket = t.task_type if t.task_type in tasks_by_type else "small"
            tasks_by_type[bucket].append(t)

        task_list_column.controls.clear()

        for task_type in TASK_TYPE_ORDER:
            group_tasks = tasks_by_type[task_type]
            header = ft.Text(
                f"{TASK_TYPE_LABELS[task_type]} ({format_limit_count(task_type, len(group_tasks))})",
                size=16,
                weight=ft.FontWeight.BOLD,
            )
            task_list_column.controls.append(header)

            if not group_tasks:
                task_list_column.controls.append(
                    ft.Text("No tasks in this group.", color=ft.Colors.BLUE_GREY_700)
                )
                task_list_column.controls.append(ft.Divider(height=12))
                continue

            def open_task_editor(task: Task) -> None:
                nonlocal task_edit_dialog

                if task_edit_dialog is not None:
                    close_dialog(task_edit_dialog)
                    task_edit_dialog = None

                type_field = ft.Dropdown(
                    label="Type",
                    value=task.task_type,
                    width=220,
                    options=[
                        ft.dropdown.Option(key=k, text=TASK_TYPE_LABELS[k])
                        for k in TASK_TYPE_ORDER
                    ],
                )
                title_field = ft.TextField(label="Task name", value=task.title, width=360)
                estimated_field = ft.TextField(
                    label="Estimated length (h)",
                    value=f"{task.estimated_hours:g}",
                    width=220,
                )
                start_field = ft.TextField(
                    label="Start time (HH:MM)", value=task.start_time, width=220
                )
                done_field = ft.Checkbox(label="Done", value=task.is_done)

                def dismiss_editor(_: ft.ControlEvent | None = None) -> None:
                    nonlocal task_edit_dialog
                    if task_edit_dialog is not None:
                        close_dialog(task_edit_dialog)
                        task_edit_dialog = None

                def save_task(_: ft.ControlEvent) -> None:
                    if not validate_time_or_empty(start_field.value):
                        show_message("Start time must use HH:MM (24-hour).", False)
                        page.update()
                        return

                    try:
                        ok, msg = db.update_task(
                            task_id=task.id,
                            day=task.day,
                            task_type=type_field.value or "small",
                            title=title_field.value,
                            estimated_hours=parse_hours(estimated_field.value),
                            start_time=start_field.value,
                            spent_hours=task.spent_hours,
                            is_done=bool(done_field.value),
                        )
                    except ValueError:
                        show_message("Estimated/spent hours must be numeric.", False)
                        page.update()
                        return

                    show_message(msg, ok)
                    if ok:
                        dismiss_editor()
                    refresh_tasks()
                    page.update()

                def remove_task(_: ft.ControlEvent) -> None:
                    db.delete_task(task.id)
                    dismiss_editor()
                    show_message("Task deleted.")
                    refresh_tasks()
                    page.update()

                task_edit_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Edit task"),
                    content=ft.Column(
                        tight=True,
                        controls=[
                            type_field,
                            title_field,
                            ft.Row(controls=[estimated_field, start_field], wrap=True),
                            done_field,
                        ],
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=dismiss_editor),
                        ft.OutlinedButton("Delete", on_click=remove_task),
                        ft.ElevatedButton("Save", on_click=save_task),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                open_dialog(task_edit_dialog)

            def mark_task_done(task: Task) -> None:
                if task.is_done:
                    show_message("Task is already done.")
                    page.update()
                    return
                ok, msg = db.update_task(
                    task_id=task.id,
                    day=task.day,
                    task_type=task.task_type,
                    title=task.title,
                    estimated_hours=task.estimated_hours,
                    start_time=task.start_time,
                    spent_hours=task.spent_hours,
                    is_done=True,
                )
                show_message("Task marked done." if ok else msg, ok)
                refresh_tasks()
                page.update()

            for t in group_tasks:
                start_text = t.start_time if t.start_time else "No start time"
                estimated_text = (
                    f"{t.estimated_hours:g}h" if t.estimated_hours > 0 else "No estimate"
                )
                task_list_column.controls.append(
                    ft.GestureDetector(
                        on_tap=lambda _, task=t: open_task_editor(task),
                        on_long_press=lambda _, task=t: mark_task_done(task),
                        content=ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Column(
                                        controls=[
                                            ft.Text(
                                                t.title,
                                                weight=ft.FontWeight.BOLD,
                                                color=(
                                                    ft.Colors.BLUE_GREY_500
                                                    if t.is_done
                                                    else ft.Colors.BLUE_GREY_900
                                                ),
                                            ),
                                            ft.Text(
                                                f"{TASK_TYPE_LABELS.get(t.task_type, 'Task')} | {estimated_text} | {start_text}",
                                                size=12,
                                                color=ft.Colors.BLUE_GREY_700,
                                            ),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    ft.Text(
                                        "DONE" if t.is_done else "OPEN",
                                        weight=ft.FontWeight.W_600,
                                        color=(
                                            ft.Colors.GREEN_700
                                            if t.is_done
                                            else ft.Colors.BLUE_GREY_700
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=10,
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=8,
                            bgcolor=(
                                ft.Colors.GREY_200
                                if t.is_done
                                else TASK_TYPE_COLORS.get(t.task_type, ft.Colors.BLUE_50)
                            ),
                        ),
                    )
                )

            task_list_column.controls.append(ft.Divider(height=12))

        refresh_timeline(tasks)

    def refresh_all() -> None:
        date_label.value = datetime.strftime(current_day, "%A, %B %d, %Y")
        refresh_habits()
        refresh_tasks()
        refresh_stats()

    def go_prev_day(_: ft.ControlEvent) -> None:
        nonlocal current_day
        current_day = current_day - timedelta(days=1)
        refresh_all()
        page.update()

    def go_next_day(_: ft.ControlEvent) -> None:
        nonlocal current_day
        current_day = current_day + timedelta(days=1)
        refresh_all()
        page.update()

    def add_habit(_: ft.ControlEvent) -> None:
        ok, msg = db.add_habit(add_habit_input.value)
        show_message(msg, ok)
        if ok:
            add_habit_input.value = ""
        refresh_all()
        page.update()

    def add_task(_: ft.ControlEvent) -> None:
        if not validate_time_or_empty(task_time_input.value):
            show_message("Start time must use HH:MM (24-hour).", False)
            show_task_form_message("Start time must use HH:MM (24-hour).", False)
            page.update()
            return

        try:
            estimated = parse_hours(task_estimated_input.value)
        except ValueError:
            show_message("Estimated length must be numeric hours (for example, 0.5).", False)
            show_task_form_message(
                "Estimated length must be numeric hours (for example, 0.5).", False
            )
            page.update()
            return

        try:
            ok, msg = db.add_task(
                day=selected_day_str(),
                task_type=add_task_type.value or "small",
                title=task_title_input.value,
                estimated_hours=estimated,
                start_time=task_time_input.value,
            )
        except Exception as ex:
            ok, msg = False, f"Failed to add task: {ex}"
        show_message(msg, ok)
        show_task_form_message(msg, ok)
        if ok:
            task_title_input.value = ""
            task_time_input.value = ""
            task_estimated_input.value = ""
            task_title_input.focus()
        refresh_tasks()
        page.update()

    task_title_input.on_submit = add_task
    task_estimated_input.on_submit = add_task
    task_time_input.on_submit = add_task

    def save_day_start(_: ft.ControlEvent) -> None:
        if not validate_time_or_empty(day_start_input.value):
            show_message("Day start must use HH:MM (24-hour).", False)
            page.update()
            return
        new_value = day_start_input.value.strip() or "09:00"
        db.set_setting("day_start", new_value)
        day_start_input.value = new_value
        show_message("Day start saved.")
        refresh_tasks()
        page.update()

    quote_dialog: ft.AlertDialog | None = None

    def open_dialog(dialog: ft.AlertDialog) -> None:
        if hasattr(page, "open"):
            page.open(dialog)
            return
        if hasattr(page, "show_dialog"):
            page.show_dialog(dialog)
            return
        page.dialog = dialog
        dialog.open = True
        page.update()

    def close_dialog(dialog: ft.AlertDialog) -> None:
        if hasattr(page, "close"):
            page.close(dialog)
            return
        dialog.open = False
        if hasattr(page, "dialog"):
            page.dialog = None
        page.update()

    def dismiss_daily_quote(_: ft.ControlEvent | None = None) -> None:
        nonlocal quote_dialog
        today_str = date.today().isoformat()
        db.set_setting("quote_dismissed_day", today_str)
        if quote_dialog is not None:
            close_dialog(quote_dialog)
            quote_dialog = None

    def show_daily_quote_if_needed() -> None:
        nonlocal quote_dialog
        today = date.today()
        today_str = today.isoformat()
        dismissed_day = db.get_setting("quote_dismissed_day", "")
        if dismissed_day == today_str:
            return

        quote, author = db.get_quote_for_date(today)
        quote_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Quote of the Day"),
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Text(f'"{quote}"', italic=True, selectable=True),
                    ft.Text(f"- {author}", weight=ft.FontWeight.W_600),
                ],
            ),
            actions=[ft.ElevatedButton("Start day", on_click=dismiss_daily_quote)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        open_dialog(quote_dialog)

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.ElevatedButton("<", on_click=go_prev_day),
                        date_label,
                        ft.ElevatedButton(">", on_click=go_next_day),
                        day_start_input,
                        ft.ElevatedButton("Save day start", on_click=save_day_start),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                status_text,
                ft.Divider(),
                ft.Text("Daily Habits", size=20, weight=ft.FontWeight.BOLD),
                ft.Row(
                    controls=[
                        add_habit_input,
                        ft.ElevatedButton("Add habit", on_click=add_habit),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                habit_column,
                ft.Divider(),
                ft.Text("Tasks", size=20, weight=ft.FontWeight.BOLD),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "Task List",
                                        size=18,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Add task for selected day",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Row(
                                        controls=[
                                            add_task_type,
                                            task_title_input,
                                        ],
                                        wrap=False,
                                        spacing=10,
                                    ),
                                    ft.Row(
                                        controls=[
                                            task_estimated_input,
                                            task_time_input,
                                            ft.ElevatedButton(
                                                "Add task for this day",
                                                on_click=add_task,
                                            ),
                                        ],
                                        wrap=False,
                                        spacing=10,
                                    ),
                                    task_form_status,
                                    ft.Text(
                                        "Short tap: edit task | Long press: mark done",
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_700,
                                    ),
                                    ft.Divider(height=14),
                                    task_list_column,
                                ]
                            ),
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=10,
                            padding=12,
                            col={"xs": 12, "md": 7},
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        "Time Line",
                                        size=18,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    timeline_column,
                                ]
                            ),
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=10,
                            padding=12,
                            col={"xs": 12, "md": 5},
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Text("Habit Completion Stats", size=20, weight=ft.FontWeight.BOLD),
                week_stat,
                month_stat,
                year_stat,
            ]
        )
    )

    refresh_all()
    show_daily_quote_if_needed()
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
