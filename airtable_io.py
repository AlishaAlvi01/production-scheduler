"""
Airtable read/write with snapshot + rollback.

Before writing a new schedule, the current planned values of every touched
record are saved to snapshots/<timestamp>.json. `rollback` restores them.

Field names come from config.json so this fits any base layout.
Uses returnFieldsByFieldId=false (names) for readability; switch to field IDs
if your field names change often.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from .model import Assignment, Order, Task, Worker

API = "https://api.airtable.com/v0"
SNAP_DIR = Path("snapshots")


class Airtable:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = os.environ["AIRTABLE_BASE_ID"]
        self.h = {"Authorization": f"Bearer {os.environ['AIRTABLE_TOKEN']}", "Content-Type": "application/json"}

    # ---------- reads ----------
    def _all(self, table: str, formula: str | None = None) -> list[dict]:
        out, offset = [], None
        while True:
            params = {"pageSize": 100}
            if formula:
                params["filterByFormula"] = formula
            if offset:
                params["offset"] = offset
            r = requests.get(f"{API}/{self.base}/{table}", headers=self.h, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            out += data["records"]
            offset = data.get("offset")
            if not offset:
                return out
            time.sleep(0.21)  # stay under 5 req/s

    def load(self, plan_start: datetime):
        from .report import working_hours_until
        c = self.cfg
        tf, wf, of = c["task_fields"], c["worker_fields"], c["order_fields"]

        workers = [
            Worker(r["id"], r["fields"].get(wf["name"], r["id"]), r["fields"].get(wf["skills"], []))
            for r in self._all(c["workers_table"], wf.get("active_formula"))
        ]

        task_recs = self._all(c["tasks_table"], tf.get("open_formula"))
        tasks = []
        for r in task_recs:
            f = r["fields"]
            assignee = (f.get(tf["assignee"]) or [None])[0]
            tasks.append(Task(
                id=r["id"],
                order_id=(f.get(tf["order"]) or ["?"])[0],
                skill=f.get(tf["skill"], ""),
                duration=max(1, int(round(float(f.get(tf["remaining_hours"], 1))))),
                predecessors=f.get(tf["predecessors"], []),
                status={"In Progress": "in_progress", "Done": "done"}.get(f.get(tf["status"]), "todo"),
                assignee=assignee,
                title=f.get(tf["title"], ""),
            ))

        order_ids = {t.order_id for t in tasks}
        orders = []
        for r in self._all(c["orders_table"]):
            if r["id"] not in order_ids:
                continue
            due = datetime.fromisoformat(r["fields"][of["due_date"]])
            orders.append(Order(r["id"], working_hours_until(due, plan_start), int(r["fields"].get(of["priority"], 1))))
        return tasks, workers, orders

    # ---------- writes ----------
    def snapshot(self, task_ids: list[str]) -> Path:
        tf = self.cfg["task_fields"]
        keep = [tf["planned_start"], tf["planned_end"], tf["planned_assignee"]]
        recs = [r for r in self._all(self.cfg["tasks_table"]) if r["id"] in set(task_ids)]
        snap = {r["id"]: {k: r["fields"].get(k) for k in keep} for r in recs}
        SNAP_DIR.mkdir(exist_ok=True)
        path = SNAP_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(snap, indent=1))
        return path

    def write(self, assignments: list[Assignment], plan_start: datetime) -> None:
        from .report import to_datetime
        tf = self.cfg["task_fields"]
        updates = [
            {"id": a.task_id, "fields": {
                tf["planned_start"]: to_datetime(a.start, plan_start).isoformat(),
                tf["planned_end"]: to_datetime(a.end, plan_start).isoformat(),
                tf["planned_assignee"]: [a.worker_id],
            }}
            for a in assignments
        ]
        self._patch(updates)

    def rollback(self, snapshot_path: Path) -> int:
        snap = json.loads(Path(snapshot_path).read_text())
        updates = [{"id": rid, "fields": fields} for rid, fields in snap.items()]
        self._patch(updates)
        return len(updates)

    def _patch(self, updates: list[dict]) -> None:
        for i in range(0, len(updates), 10):  # Airtable: max 10 records per request
            r = requests.patch(f"{API}/{self.base}/{self.cfg['tasks_table']}", headers=self.h,
                               json={"records": updates[i:i + 10], "typecast": True}, timeout=30)
            r.raise_for_status()
            time.sleep(0.21)
