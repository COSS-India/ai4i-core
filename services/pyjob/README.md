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
