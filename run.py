"""
CLI.

  python run.py --sample                 # solve the bundled sample, print report
  python run.py --airtable --dry-run     # read Airtable, solve, print, don't write
  python run.py --airtable               # snapshot, then write the new plan
  python run.py --rollback snapshots/20260101-020000.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from scheduler.model import Order, Task, Worker, solve
from scheduler.report import print_report


def load_sample(path: Path):
    d = json.loads(path.read_text())
    return (
        [Task(**t) for t in d["tasks"]],
        [Worker(**w) for w in d["workers"]],
        [Order(**o) for o in d["orders"]],
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", action="store_true")
    src.add_argument("--airtable", action="store_true")
    src.add_argument("--rollback", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--time-limit", type=float, default=30.0)
    args = ap.parse_args()

    plan_start = datetime.now().replace(minute=0, second=0, microsecond=0)
    cfg = json.loads(Path("config.json").read_text()) if Path("config.json").exists() else {}

    if args.rollback:
        from scheduler.airtable_io import Airtable
        n = Airtable(cfg).rollback(args.rollback)
        print(f"Rolled back {n} records from {args.rollback}")
        return

    if args.sample:
        tasks, workers, orders = load_sample(Path("sample_data.json"))
        at = None
    else:
        from scheduler.airtable_io import Airtable
        at = Airtable(cfg)
        tasks, workers, orders = at.load(plan_start)

    result = solve(tasks, workers, orders, time_limit_s=args.time_limit)
    print_report(result, tasks, workers, orders, plan_start)

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        raise SystemExit("No feasible schedule — check skills, predecessors and due dates.")

    if at and not args.dry_run:
        snap = at.snapshot([a.task_id for a in result.assignments])
        at.write(result.assignments, plan_start)
        print(f"\nWrote {len(result.assignments)} assignments. Snapshot: {snap}")


if __name__ == "__main__":
    main()
