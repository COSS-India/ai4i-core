# Usage Dashboard backfill (one-off)

Copies Prometheus' daily **LLM** totals for the days **before `usage_events` began** into
`daily_usage`, as estimated rows (`source = 'backfill'`). Recorded data (`source = 'rollup'`,
from `usage_events`) is never touched. Run it **once per environment**, by hand: it is not a
scheduled job.

## Prerequisites

1. The migration that adds `daily_usage.source` is applied.
2. Prometheus still holds every day from `BACKFILL_FROM` on, including its start (it drops its
   oldest day every day, so run this sooner rather than later). A day whose start Prometheus no
   longer has would count every counter's lifetime total as that day's usage.
3. `BACKFILL_TO` is before the day `usage_events` begins (the job refuses otherwise).
4. The dashboard shows the rows where platform-core has `USAGE_DAILY_ROLLUP_ENABLED=true`.

## Run

```bash
cd services/pyjob
cp backfill/env.template backfill/.env      # then fill in the DB, Prometheus and days
python -m backfill
```

The backfill reads `backfill/.env` and the environment (which overrides it). **Fill in every
database variable**: one left out (or commented out) can still be taken from
`services/pyjob/.env`, if there is one, since the connection goes through pyjob's own settings.

| Variable | Meaning |
|---|---|
| `PROMETHEUS_URL` | Prometheus to read from. Required. |
| `BACKFILL_FROM` | First IST day to backfill (`YYYY-MM-DD`), inclusive. Required. |
| `BACKFILL_TO` | Last IST day to backfill (`YYYY-MM-DD`), inclusive. Required; a past day before `usage_events` begins. |
| `PROMETHEUS_API_PATH_LABEL` | Label carrying the request path: `exported_endpoint` on k8s (default), `endpoint` on local docker-compose. |
| `PROMETHEUS_TIMEOUT_SECONDS` | Per-query timeout (default 60). |

The database variables (`PLATFORM_CORE_DB_*`, `AUTH_DB_*`, `AUTH_SERVICE_DB_NAME`, falling back
to `POSTGRES_*`; `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) have the same names as pyjob's, and are in
`backfill/env.template` too; `backfill/.env` is loaded into the environment before the databases
open, so these are the ones used.

## What it does

1. Checks the dates, and that `usage_events` has no rows before the end of `BACKFILL_TO`.
2. Loads into memory, once, what the rows need: institutions (name, budget, current tier),
   applications, single-key applications, tiers, LLM services with their model and prices, and
   the LLM inference type.
3. For each day, in order:
   1. asks Prometheus for the day's LLM requests, successful requests and prompt / completion
      tokens, per institution, application and service: the queries the Prometheus-backed
      dashboard used (release-2.8), evaluated at the day's end;
   2. builds one row per institution, application and service: cost = prompt tokens × the
      service's input price + completion tokens × its output price;
   3. replaces that day's backfill rows with them, in one transaction.

Re-running is safe: each day's earlier backfill rows are replaced. Rows for a past month without its
own `daily_usage` partition land in the table's DEFAULT partition; the dashboard and undo read them
the same.

## Undo

```bash
cd services/pyjob
python -m backfill undo
```

Deletes every `source = 'backfill'` row and nothing else. Safe to re-run.

## Notes / limitations

These rows are **estimates**, from Prometheus' counter growth, not a replay of events:

- LLM only (`/api/v1/chat`, `/api/v1/chat/completions` and LLM tokens).
- Cost uses each service's **current** price; a service with no price (or not an LLM service in
  `mm_services`) keeps its tokens at ₹0.
- Institution tier and allocated budget are **current**, not point-in-time.
- `api_key_id` is set only when an application has exactly one key, else NULL.
- `cached_input_units` is 0 (not recorded before 2026-10-09).
- `billing_month` is the day's month.
