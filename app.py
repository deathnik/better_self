import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft

DB_PATH = Path(__file__).with_name("journal.db")


@dataclass
class Habit:
    id: int
    name: str


@dataclass
class Task:
    id: int
    day: str
    title: str
    scheduled_time: str
    planned_minutes: int
    spent_minutes: int


class JournalDB:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

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
                title TEXT NOT NULL,
                scheduled_time TEXT,
                planned_minutes INTEGER NOT NULL DEFAULT 0,
                spent_minutes INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.commit()

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

    def add_task(self, day: str, title: str, scheduled_time: str, planned_minutes: int) -> tuple[bool, str]:
        clean_title = title.strip()
        if not clean_title:
            return False, "Task title is required."
        if planned_minutes < 0:
            return False, "Needed time cannot be negative."
        self.conn.execute(
            """
            INSERT INTO tasks(day, title, scheduled_time, planned_minutes, spent_minutes)
            VALUES (?, ?, ?, ?, 0)
            """,
            (day, clean_title, scheduled_time.strip(), planned_minutes),
        )
        self.conn.commit()
        return True, "Task added."

    def list_tasks(self, day: str) -> list[Task]:
        rows = self.conn.execute(
            """
            SELECT id, day, title, scheduled_time, planned_minutes, spent_minutes
            FROM tasks
            WHERE day = ?
            ORDER BY COALESCE(NULLIF(scheduled_time, ''), '99:99'), id
            """,
            (day,),
        ).fetchall()
        return [
            Task(
                id=row["id"],
                day=row["day"],
                title=row["title"],
                scheduled_time=row["scheduled_time"] or "",
                planned_minutes=row["planned_minutes"],
                spent_minutes=row["spent_minutes"],
            )
            for row in rows
        ]

    def update_task(
        self,
        task_id: int,
        title: str,
        scheduled_time: str,
        planned_minutes: int,
        spent_minutes: int,
    ) -> tuple[bool, str]:
        clean_title = title.strip()
        if not clean_title:
            return False, "Task title is required."
        if planned_minutes < 0 or spent_minutes < 0:
            return False, "Times cannot be negative."

        self.conn.execute(
            """
            UPDATE tasks
            SET title = ?, scheduled_time = ?, planned_minutes = ?, spent_minutes = ?
            WHERE id = ?
            """,
            (clean_title, scheduled_time.strip(), planned_minutes, spent_minutes, task_id),
        )
        self.conn.commit()
        return True, "Task saved."

    def delete_task(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()


def parse_minutes(value: str) -> int:
    raw = value.strip()
    if not raw:
        return 0
    return int(raw)


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


def main(page: ft.Page) -> None:
    db = JournalDB(DB_PATH)
    current_day = date.today()

    page.title = "Daily Journal"
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 950
    page.window_height = 820
    page.scroll = ft.ScrollMode.AUTO

    date_label = ft.Text(size=22, weight=ft.FontWeight.BOLD)
    status_text = ft.Text(color=ft.Colors.BLUE_GREY_700)

    habit_column = ft.Column(spacing=8)
    task_column = ft.Column(spacing=10)

    week_stat = ft.Text()
    month_stat = ft.Text()
    year_stat = ft.Text()

    add_habit_input = ft.TextField(label="New habit", expand=True)

    task_title_input = ft.TextField(label="Task", expand=True)
    task_time_input = ft.TextField(label="Timing (HH:MM)", width=150)
    task_needed_input = ft.TextField(label="Needed time (min)", width=170)

    def selected_day_str() -> str:
        return current_day.isoformat()

    def show_message(message: str, ok: bool = True) -> None:
        status_text.value = message
        status_text.color = ft.Colors.GREEN_700 if ok else ft.Colors.RED_700

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

    def refresh_tasks() -> None:
        task_column.controls.clear()
        tasks = db.list_tasks(selected_day_str())

        if not tasks:
            task_column.controls.append(ft.Text("No tasks for this day."))
            return

        for t in tasks:
            title = ft.TextField(value=t.title, expand=True)
            sched = ft.TextField(value=t.scheduled_time, width=140)
            planned = ft.TextField(value=str(t.planned_minutes), width=120)
            spent = ft.TextField(value=str(t.spent_minutes), width=120)
            save_btn = ft.ElevatedButton("Save")
            delete_btn = ft.OutlinedButton("Delete")

            def save_task(_: ft.ControlEvent, task_id: int = t.id, title_f: ft.TextField = title, sched_f: ft.TextField = sched, planned_f: ft.TextField = planned, spent_f: ft.TextField = spent) -> None:
                try:
                    ok, msg = db.update_task(
                        task_id=task_id,
                        title=title_f.value,
                        scheduled_time=sched_f.value,
                        planned_minutes=parse_minutes(planned_f.value),
                        spent_minutes=parse_minutes(spent_f.value),
                    )
                    show_message(msg, ok)
                except ValueError:
                    show_message("Needed/spent time must be whole minutes.", False)
                refresh_tasks()
                page.update()

            def remove_task(_: ft.ControlEvent, task_id: int = t.id) -> None:
                db.delete_task(task_id)
                show_message("Task deleted.")
                refresh_tasks()
                page.update()

            save_btn.on_click = save_task
            delete_btn.on_click = remove_task

            task_column.controls.append(
                ft.Row(
                    controls=[title, sched, planned, spent, save_btn, delete_btn],
                    wrap=True,
                    alignment=ft.MainAxisAlignment.START,
                )
            )

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
        try:
            needed = parse_minutes(task_needed_input.value)
        except ValueError:
            show_message("Needed time must be whole minutes.", False)
            page.update()
            return

        ok, msg = db.add_task(
            day=selected_day_str(),
            title=task_title_input.value,
            scheduled_time=task_time_input.value,
            planned_minutes=needed,
        )
        show_message(msg, ok)
        if ok:
            task_title_input.value = ""
            task_time_input.value = ""
            task_needed_input.value = ""
        refresh_tasks()
        page.update()

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.ElevatedButton("<", on_click=go_prev_day),
                        date_label,
                        ft.ElevatedButton(">", on_click=go_next_day),
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
                ft.Row(
                    controls=[
                        task_title_input,
                        task_time_input,
                        task_needed_input,
                        ft.ElevatedButton("Add task", on_click=add_task),
                    ],
                    wrap=True,
                ),
                ft.Row(
                    controls=[
                        ft.Text("Task", weight=ft.FontWeight.BOLD, width=250),
                        ft.Text("Timing", weight=ft.FontWeight.BOLD, width=140),
                        ft.Text("Needed", weight=ft.FontWeight.BOLD, width=120),
                        ft.Text("Spent", weight=ft.FontWeight.BOLD, width=120),
                    ]
                ),
                task_column,
                ft.Divider(),
                ft.Text("Habit Completion Stats", size=20, weight=ft.FontWeight.BOLD),
                week_stat,
                month_stat,
                year_stat,
            ]
        )
    )

    refresh_all()
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
