# Production Scheduler (OR-Tools CP-SAT + Airtable)

Automatically plans **who does which production task, and when**, for a made-to-order workshop — then writes the plan back to Airtable every night.

Built for businesses where every order is a chain of craft steps (cutting → dyeing → embroidery → stitching → QC), each step needs a specific skill, and orders have hard due dates.

> Template repo. Generic, rebuilt reference implementation of a scheduler I built and run in production for a couture brand's workshop. No client code, data, or IDs are included. Sample data is fictional.

## What it solves

| Constraint | How |
|---|---|
| Right person for the job | Task skill must match worker skills |
| One task at a time | `NoOverlap` per worker |
| Process order | Predecessors, including parallel sub-chains that re-join (e.g. dyeing ∥ embroidery → stitching) |
| Work already started | **Frozen assignee**: in-progress tasks keep their worker and start now |
| Working hours | Time is counted in shop working hours, so long craft steps stay as one block; the report converts to calendar dates (Sundays off, configurable) |
| Due dates | Minimise priority-weighted lateness, then total makespan |

## Safety: snapshot & rollback

Before every write, the current planned values of all touched records are saved to `snapshots/<timestamp>.json` (committed by the workflow). A bad plan is one command away from undone:

```bash
python run.py --rollback snapshots/20261010-020000.json
```

## Try it locally

```bash
pip install -r requirements.txt
python run.py --sample
pytest
```

Sample output:

```
PER ORDER
order     planned finish      due                  late h  status
ORD-101   ...                 ...                       0  ON TIME
...
WORKER LOAD (hours)
  Cutter A         5
  ...
```

## Run on your Airtable base

1. Tables: **Tasks**, **Workers**, **Orders** (see `config.example.json` for fields; rename freely).
2. `cp config.example.json config.json` and map your field names.
3. `export AIRTABLE_TOKEN=... AIRTABLE_BASE_ID=...`
4. `python run.py --airtable --dry-run` → check the report → `python run.py --airtable`.

## Automate with GitHub Actions

`.github/workflows/schedule.yml` supports manual runs, dry runs, and rollback by snapshot name. Add `AIRTABLE_TOKEN` and `AIRTABLE_BASE_ID` as repo secrets, then uncomment the `schedule:` block to run it nightly.

## Author

Built by **Alisha Alvi** — automation & AI systems engineer.
[LinkedIn](https://linkedin.com/in/alisha-alvie) · [GitHub](https://github.com/AlishaAlvi01) · alishaalvi745@gmail.com
