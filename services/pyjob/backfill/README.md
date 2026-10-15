# Usage Dashboard backfill (one-off)

Reconstructs the Usage Dashboard's history for the days **before `usage_events`
began**, from Prometheus, as estimated `daily_usage` rows (`source =
'backfill'`). Recorded data (`source = 'rollup'`, from `usage_events`) is never
touched. Run it **once per environment**, by hand — it is not a scheduled job.

## Prerequisites

1. The migration that adds `daily_usage.source` is applied.
2. Prometheus is reachable and still holds the days you want to recover (it
   drops its oldest day every day — run this sooner rather than later).

## Run

```bash
cd services/pyjob
PROMETHEUS_URL=http://prometheus:9090 \
PROMETHEUS_API_PATH_LABEL=exported_endpoint \   # "endpoint" on local docker-compose
python -m backfill
```

Reads Prometheus and loads `daily_usage` in one run. Idempotent: re-running
replaces the backfilled days it reads (days Prometheus no longer has are kept).

### Optional

| Variable | Meaning |
|---|---|
| `USAGE_BACKFILL_FROM` | First IST day to backfill (`YYYY-MM-DD`). May not be earlier than the first whole day Prometheus still has; defaults to it. |
| `USAGE_BACKFILL_UNTIL` | Cut-over instant. Defaults to the IST midnight of the day the first `usage_events` row falls on. |
| `PROMETHEUS_TIMEOUT_SECONDS` | Per-request timeout (default 60). |

Database connection comes from pyjob's own settings (`bootstrap.config`); set
them as for any other job.

## Undo

```bash
cd services/pyjob
python -m backfill undo
```

Deletes every `source = 'backfill'` row and nothing else. Safe to re-run.

## Notes / limitations

These rows are **estimates** — Prometheus' own counter-growth, not a replay of
events:

- Cost uses each service's **current** price (no historical price table).
- Tenant tier / allocated budget are **current**, not point-in-time.
- `api_key_id` is set only when an application has exactly one key, else NULL.
- `cached_input_units` is 0 (not recorded before the recorded-data cut-over).
- The cut-over day's pre-first-event sliver is not captured (boundary-stop).

The dashboard marks days before the cut-over as estimated; the boundary is
derived from `usage_events`, so this job keeps no extra state table.
