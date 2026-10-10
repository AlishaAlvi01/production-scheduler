import json
from pathlib import Path

from scheduler.model import Order, Task, Worker, solve

ROOT = Path(__file__).resolve().parents[1]


def load():
    d = json.loads((ROOT / "sample_data.json").read_text())
    return [Task(**t) for t in d["tasks"]], [Worker(**w) for w in d["workers"]], [Order(**o) for o in d["orders"]]


def test_sample_is_feasible_and_respects_constraints():
    tasks, workers, orders = load()
    r = solve(tasks, workers, orders, time_limit_s=10)
    assert r.status in ("OPTIMAL", "FEASIBLE")

    by_task = {a.task_id: a for a in r.assignments}
    tmap = {t.id: t for t in tasks}
    wmap = {w.id: w for w in workers}

    # every open task scheduled once
    assert set(by_task) == {t.id for t in tasks if t.status != "done"}

    for a in r.assignments:
        t = tmap[a.task_id]
        # skill match
        assert t.skill in wmap[a.worker_id].skills or t.status == "in_progress"
        # precedence
        for p in t.predecessors:
            assert a.start >= by_task[p].end

    # frozen assignees stay put and start now
    for t in tasks:
        if t.status == "in_progress":
            assert by_task[t.id].worker_id == t.assignee
            assert by_task[t.id].start == 0

    # no worker double-booked
    for w in workers:
        ivs = sorted((a.start, a.end) for a in r.assignments if a.worker_id == w.id)
        for (s1, e1), (s2, _) in zip(ivs, ivs[1:]):
            assert s2 >= e1


def test_done_predecessors_are_ignored():
    tasks = [
        Task("a", "O1", "cut", 2, status="done"),
        Task("b", "O1", "cut", 2, predecessors=["a"]),
    ]
    r = solve(tasks, [Worker("w", "W", ["cut"])], [Order("O1", 10)], time_limit_s=5)
    assert r.status == "OPTIMAL"
    assert r.assignments[0].start == 0


def test_calendar_conversion_skips_sunday():
    from datetime import datetime
    from scheduler.report import to_datetime
    sat = datetime(2026, 10, 10, 9)  # Saturday
    assert to_datetime(0, sat) == datetime(2026, 10, 10, 10)
    assert to_datetime(8, sat) == datetime(2026, 10, 10, 18)   # closes Saturday
    assert to_datetime(9, sat) == datetime(2026, 10, 12, 11)   # Monday 11:00
