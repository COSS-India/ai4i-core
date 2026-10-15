# pyjob

Runs the platform's scheduled jobs, one job per process. Scheduling is done by k8s CronJobs, which run the image with `--job <name>`.

## Layout

```
main.py                  entry point
bootstrap/
  config.py              settings (env / .env); DB and Redis vars follow auth-service's names
  database.py            engines + sessions for the platform-core and auth DBs
  redis_client.py        get_redis(): shared async Redis client
  platform_core.py       call_internal(): POST to platform-core /internal/*
  registry.py            job discovery from jobs/*.py
  launcher.py            --job NAME | --list
jobs/                    one module per job
```

## Adding a job

Create `jobs/<name>.py`:

```python
from bootstrap.database import auth_session, platform_core_session
from bootstrap.redis_client import get_redis

async def run() -> None:
    async with platform_core_session() as session:
        ...
```

It is picked up automatically. The launcher opens the DB engines before `run()` and disposes them and the Redis client after. Add the schedule to the k8s CronJob manifest.

## Jobs

| Job | Schedule (UTC) | What it does |
|---|---|---|
| `daily_usage_consolidation` | `30 18 * * *` (00:00 IST) | Keeps `usage_events` partitioned by IST day (converts the migration's UTC month partitions, and any UTC day partitions, on its first run; creates `USAGE_EVENTS_DAYS_AHEAD` days ahead; past days are kept), then rolls the IST day that just ended and the `USAGE_ROLLUP_LOOKBACK_DAYS` before it into `daily_usage`, with `billing_month` the UTC month of `occurred_at` |
| `monthly_partition_rollover` | `0 0 1 * *` (05:30 IST) | Creates `daily_usage` month partitions `PARTITION_MONTHS_AHEAD` months ahead (moving any of their rows out of the DEFAULT partition first); past months are kept |
| `usage_backfill` | **none: run by hand, once per environment** | One-off: keeps the Usage Dashboard's history from before `usage_events` existed. Reads Prometheus' daily requests, LLM prompt/completion tokens and other units (API-key traffic) and loads them into `daily_usage` as `source = 'backfill'` rows, priced at today's prices, in one run. Needs migration `f6c8e0a2b4d7` and `PROMETHEUS_URL`. Run it as early as possible: Prometheus drops its oldest day every day. See the module docstring |
| `usage_backfill_undo` | **none: run by hand, only to undo a backfill** | Removes exactly what `usage_backfill` loaded, in one transaction: every `daily_usage` row with `source = 'backfill'` and the `usage_backfill` coverage row. Rollup rows, `usage_events`, `budget_usage` and `quota_usage` are untouched. Safe to re-run. Running `usage_backfill` again afterwards re-reads Prometheus, which may no longer hold the oldest days |
| `usage_report` | **once per period** of `USAGE_REPORT_FREQUENCY`, business hours, after `daily_usage_consolidation` (DevOps) — e.g. weekly `30 4 * * 1` (Mon 10:00 IST), monthly `30 4 1 * *` | Calls platform-core `POST /internal/usage-report/run`: emails the Usage Viewer report for the latest complete period of `USAGE_REPORT_FREQUENCY` (`monthly` or any duration — `1d`, `7d`, `14d` …; under a day in test envs only) to every Usage Viewer, logging each send. No send log or retry yet: every run sends again, so the schedule must match the frequency. Fails (exit 1) if not everyone got it — check the logs before re-running |

## Running

```bash
cp env.template .env                 # or ./scripts/setup-env.sh from the repo root
python main.py --list                # job names
python main.py --job <name>          # run one job now; exit 0 ok, 1 failed, 2 usage
```

```bash
docker build -t pyjob .
docker run --env-file .env pyjob --job <name>
```
