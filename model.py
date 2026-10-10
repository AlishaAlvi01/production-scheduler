"""
Core CP-SAT scheduling model.

Problem: assign every production task to an eligible worker and a start time so that
  - each worker does one task at a time
  - tasks respect their predecessors (supports parallel sub-chains that re-join)
  - tasks already in progress keep their worker (frozen assignee) and start now
and we minimise weighted lateness against each order's due date, then makespan.

Time unit: SHOP working hours from the planning start (hour 0 = now). Nights and
days off are simply not on the timeline; report.py converts back to calendar time.
This keeps long craft tasks (e.g. 16h of embroidery) as single uninterrupted blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ortools.sat.python import cp_model


@dataclass
class Task:
    id: str
    order_id: str
    skill: str
    duration: int                      # hours remaining
    predecessors: list[str] = field(default_factory=list)
    status: str = "todo"               # todo | in_progress | done
    assignee: str | None = None        # current assignee (frozen if in_progress)
    title: str = ""


@dataclass
class Worker:
    id: str
    name: str
    skills: list[str]


@dataclass
class Order:
    id: str
    due_hour: int                      # due date expressed in working hours from now
    priority: int = 1                  # weight for lateness


@dataclass
class Assignment:
    task_id: str
    worker_id: str
    start: int
    end: int


@dataclass
class Result:
    status: str
    assignments: list[Assignment]
    order_finish: dict[str, int]
    objective: float | None


def solve(
    tasks: list[Task],
    workers: list[Worker],
    orders: list[Order],
    horizon_hours: int | None = None,
    time_limit_s: float = 30.0,
) -> Result:
    """Build and solve the model. All times are in shop working hours."""
    open_tasks = [t for t in tasks if t.status != "done"]
    by_id = {t.id: t for t in open_tasks}
    done_ids = {t.id for t in tasks if t.status == "done"}
    horizon = horizon_hours or (sum(t.duration for t in tasks) + max([o.due_hour for o in orders] + [0]))

    m = cp_model.CpModel()
    start, end, chosen = {}, {}, {}
    worker_intervals: dict[str, list] = {w.id: [] for w in workers}

    for t in open_tasks:
        start[t.id] = m.NewIntVar(0, horizon, f"s_{t.id}")
        end[t.id] = m.NewIntVar(0, horizon, f"e_{t.id}")

        if t.status == "in_progress" and t.assignee:
            eligible = [w for w in workers if w.id == t.assignee]  # frozen assignee
            m.Add(start[t.id] == 0)
        else:
            eligible = [w for w in workers if t.skill in w.skills]

        if not eligible:
            raise ValueError(f"No eligible worker for task {t.id} (skill '{t.skill}')")

        lits = []
        for w in eligible:
            lit = m.NewBoolVar(f"x_{t.id}_{w.id}")
            iv = m.NewOptionalIntervalVar(start[t.id], t.duration, end[t.id], lit, f"iv_{t.id}_{w.id}")
            worker_intervals[w.id].append(iv)
            chosen[(t.id, w.id)] = lit
            lits.append(lit)
        m.AddExactlyOne(lits)

    # Precedence (predecessors already done are ignored)
    for t in open_tasks:
        for p in t.predecessors:
            if p in done_ids:
                continue
            if p not in by_id:
                raise ValueError(f"Task {t.id} depends on unknown task {p}")
            m.Add(start[t.id] >= end[p])

    # One task at a time per worker
    for w in workers:
        m.AddNoOverlap(worker_intervals[w.id])

    # Order finish + weighted lateness
    finish, late_terms = {}, []
    for o in orders:
        o_tasks = [t for t in open_tasks if t.order_id == o.id]
        if not o_tasks:
            continue
        f = m.NewIntVar(0, horizon, f"finish_{o.id}")
        m.AddMaxEquality(f, [end[t.id] for t in o_tasks])
        late = m.NewIntVar(0, horizon, f"late_{o.id}")
        m.Add(late >= f - o.due_hour)
        finish[o.id] = f
        late_terms.append(o.priority * late)

    makespan = m.NewIntVar(0, horizon, "makespan")
    if open_tasks:
        m.AddMaxEquality(makespan, list(end.values()))

    # Lateness dominates; makespan breaks ties.
    m.Minimize(1000 * sum(late_terms) + makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    status = solver.Solve(m)
    name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result(name, [], {}, None)

    out = []
    for t in open_tasks:
        for w in workers:
            lit = chosen.get((t.id, w.id))
            if lit is not None and solver.Value(lit):
                out.append(Assignment(t.id, w.id, solver.Value(start[t.id]), solver.Value(end[t.id])))
    out.sort(key=lambda a: (a.start, a.worker_id))
    return Result(name, out, {k: solver.Value(v) for k, v in finish.items()}, solver.ObjectiveValue())
