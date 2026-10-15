# usage-backfill

One-off scripts that keep the Usage Dashboard's history from before `usage_events` existed. They read
Prometheus' daily totals (API-key traffic) and store them in `daily_usage` as estimates
(`source = 'backfill'`), with cost at each service's current price.

| Script | What it does |
|---|---|
| `usage_backfill.py` | Reads Prometheus and loads `daily_usage`, in one run. Covers the first whole IST day after Prometheus' oldest sample (looked up each run) up to the first `usage_events` row, so nothing is counted twice. Then rolls up the day it ends on (it ends mid-day), so that day's recorded part is read too. Records the span in `usage_backfill`. Re-running gives the same rows for the days Prometheus still has. |
| `usage_backfill_undo.py` | Removes exactly what the backfill wrote, in one transaction: the `source = 'backfill'` rows and the `usage_backfill` row. Rollup rows, `usage_events`, `budget_usage` and `quota_usage` are untouched. Safe to re-run. |

The full mapping (Prometheus metrics → `daily_usage` columns) and limitations are in `usage_backfill.py`'s docstring.

## Before running
- Migration `f6c8e0a2b4d7` applied (`daily_usage.source`, `usage_backfill`).
- The dashboard shows the rows only where platform-core has `USAGE_DAILY_ROLLUP_ENABLED=true`.
- Run it as early as possible in each environment: Prometheus drops its oldest day every day.
- The scripts use pyjob's code and settings (`services/pyjob`), so install its requirements
  (`pip install -r services/pyjob/requirements.txt`) and set its database variables, in the environment
  or a `.env` in the current directory: `PLATFORM_CORE_DB_*` and `AUTH_DB_*`, falling back to `POSTGRES_*`
  (see `services/pyjob/env.template`).

## Running
From the repository root:

```bash
python scripts/usage-backfill/usage_backfill.py --prometheus-url http://prometheus:9090
```

| Option | Default | |
|---|---|---|
| `--prometheus-url` | required | Base URL of the Prometheus to read |
| `--path-label` | `exported_endpoint` | Label carrying the request path: `exported_endpoint` behind a k8s ServiceMonitor, `endpoint` on local docker-compose |
| `--from` | first whole day after Prometheus' oldest sample | First IST day, `YYYY-MM-DD`; an earlier day is refused (it would overcount) |
| `--until` | first `usage_events` row | Backfill up to this instant (ISO 8601, IST without an offset) |
| `--timeout` | `60` | Seconds per Prometheus query |

## Undoing

```bash
python scripts/usage-backfill/usage_backfill_undo.py
```

Running the backfill again afterwards re-reads Prometheus, which may no longer hold the oldest days.

## Tests

```bash
python -m pytest scripts/usage-backfill/tests
```
