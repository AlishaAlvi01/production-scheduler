"""Per-order and per-worker reports from a solved schedule."""

from __future__ import annotations

from datetime import datetime, timedelta

from .model import Order, Result, Task, Worker


SHOP_OPEN_HOUR = 10      # shop opens 10:00
SHOP_HOURS = 8           # working hours per day
WORK_DAYS = {0, 1, 2, 3, 4, 5}  # Mon-Sat (Sunday off)


def to_datetime(work_hour: int, plan_start: datetime) -> datetime:
    """Convert shop working hours from plan_start into a calendar datetime."""
    day = plan_start.replace(hour=SHOP_OPEN_HOUR, minute=0, second=0, microsecond=0)
    while day.weekday() not in WORK_DAYS:
        day += timedelta(days=1)
    days, rem = divmod(work_hour, SHOP_HOURS)
    if work_hour > 0 and rem == 0:  # an end exactly at closing time stays on that day
        days, rem = days - 1, SHOP_HOURS
    while days:
        day += timedelta(days=1)
        if day.weekday() in WORK_DAYS:
            days -= 1
    return day + timedelta(hours=rem)


def working_hours_until(due: datetime, plan_start: datetime) -> int:
    """Approximate shop working hours between now and a due date."""
    h, d = 0, plan_start.date()
    while d < due.date():
        if d.weekday() in WORK_DAYS:
            h += SHOP_HOURS
        d += timedelta(days=1)
    return h


def per_order(result: Result, orders: list[Order], plan_start: datetime) -> list[dict]:
    rows = []
    for o in orders:
        if o.id not in result.order_finish:
            continue
        fin = result.order_finish[o.id]
        rows.append(
            {
                "order": o.id,
                "planned_finish": to_datetime(fin, plan_start).strftime("%Y-%m-%d %H:%M"),
                "due": to_datetime(o.due_hour, plan_start).strftime("%Y-%m-%d %H:%M"),
                "late_hours": max(0, fin - o.due_hour),
                "status": "ON TIME" if fin <= o.due_hour else "LATE",
            }
        )
    return sorted(rows, key=lambda r: (-r["late_hours"], r["order"]))


def per_worker(result: Result, workers: list[Worker], tasks: list[Task]) -> dict[str, int]:
    load = {w.name: 0 for w in workers}
    names = {w.id: w.name for w in workers}
    dur = {t.id: t.duration for t in tasks}
    for a in result.assignments:
        load[names[a.worker_id]] += dur[a.task_id]
    return load


def print_report(result: Result, tasks, workers, orders, plan_start: datetime) -> None:
    print(f"\nSolver status: {result.status}   objective: {result.objective}")
    print("\nPER ORDER")
    print(f"{'order':<10}{'planned finish':<20}{'due':<20}{'late h':>7}  status")
    for r in per_order(result, orders, plan_start):
        print(f"{r['order']:<10}{r['planned_finish']:<20}{r['due']:<20}{r['late_hours']:>7}  {r['status']}")
    print("\nWORKER LOAD (hours)")
    for name, h in per_worker(result, workers, tasks).items():
        print(f"  {name:<14}{h:>4}")
