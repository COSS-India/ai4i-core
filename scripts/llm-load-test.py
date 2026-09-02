#!/usr/bin/env python3
"""
Fires N identical OpenAI-compatible chat-completions requests at the
AI4I dev gateway (dev.ai4inclusion.org) and records input/output/token
counts for every call.

Every request sends the EXACT SAME input string, so prompt_tokens should
stay identical across all runs (barring server-side tokenizer nondeterminism).
completion_tokens/output text can vary per call since model sampling is not
necessarily deterministic.

Setup
-----
    pip install requests
    export AI4I_API_KEY="<your bearer token>"      # PowerShell: $env:AI4I_API_KEY = "..."

Then fill in MODEL_ID below with the real service/model id for the LLM
service you want to hit, and run:

    python scripts/llm-load-test.py

Requests run concurrently across a small thread pool (see CONCURRENCY below)
since each call is I/O-bound. Results are printed to the console as they
complete (order is completion order, not request order — see the "req #N"
tag on each line) and written incrementally (row-by-row, flushed after every
request) to OUTPUT_CSV so a Ctrl+C partway through still leaves a usable file.
"""

import csv
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config — edit these before running
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://dev.ai4inclusion.org"
CHAT_COMPLETIONS_PATH = "/api/v1/chat/completions"

MODEL_ID = "aug-20-llm-2/Automation-ServiceID-v3/"  # <-- fill this in

# Same input every time -> same prompt token count every time.
INPUT_TEXT = "Summarize the importance of clean drinking water for rural communities briefly."
assert 50 <= len(INPUT_TEXT) <= 100, f"INPUT_TEXT must be 50-100 chars, got {len(INPUT_TEXT)}"

NUM_REQUESTS = 500
# How many requests run at once. HTTP calls are I/O-bound, so a thread pool is
# enough (no need for asyncio). Keep this modest on a shared dev environment —
# raise it if the endpoint tolerates more, lower it if you start seeing
# timeouts/429s/connection errors.
CONCURRENCY = 10
REQUEST_TIMEOUT_S = 60
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "llm-load-test-results.csv")

API_KEY = os.environ.get("AI4I_API_KEY")
if not API_KEY:
    sys.exit("ERROR: set the AI4I_API_KEY environment variable before running this script.")

# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "index",
    "timestamp_utc",
    "status",
    "http_status",
    "input",
    "output",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "error",
]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def send_one(session: requests.Session, index: int) -> dict:
    """Send a single chat-completions request and return a result row."""
    payload = {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": INPUT_TEXT}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    row = {
        "index": index,
        "timestamp_utc": now_utc_iso(),
        "status": "error",
        "http_status": "",
        "input": INPUT_TEXT,
        "output": "",
        "prompt_tokens": "",
        "completion_tokens": "",
        "total_tokens": "",
        "latency_ms": "",
        "error": "",
    }

    start = time.perf_counter()
    try:
        resp = session.post(
            f"{BASE_URL}{CHAT_COMPLETIONS_PATH}",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_S,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        row["latency_ms"] = round(elapsed_ms, 1)
        row["http_status"] = resp.status_code

        if resp.status_code >= 400:
            row["error"] = resp.text[:500]
            return row

        data = resp.json()
        output_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        usage = data.get("usage", {}) or {}

        row["status"] = "ok"
        row["output"] = output_text
        row["prompt_tokens"] = usage.get("prompt_tokens", "")
        row["completion_tokens"] = usage.get("completion_tokens", "")
        row["total_tokens"] = usage.get("total_tokens", "")
        return row

    except requests.RequestException as exc:
        row["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        row["error"] = str(exc)
        return row


def main() -> None:
    run_start = datetime.now(timezone.utc)
    print("=" * 78)
    print("AI4I LLM load test")
    print(f"  endpoint       : {BASE_URL}{CHAT_COMPLETIONS_PATH}")
    print(f"  model          : {MODEL_ID}")
    print(f"  requests       : {NUM_REQUESTS} (concurrency={CONCURRENCY})")
    print(f"  input ({len(INPUT_TEXT)} chars): {INPUT_TEXT!r}")
    print(f"  output file    : {OUTPUT_CSV}")
    print(f"  start time     : {run_start.isoformat(timespec='seconds')}")
    print("=" * 78)

    ok_count = 0
    err_count = 0
    completed = 0
    prompt_tokens_seen = set()
    total_completion_tokens = 0
    total_tokens_sum = 0
    latencies = []
    # Requests complete out of order under concurrency; this lock keeps CSV
    # rows and console lines from interleaving across worker threads.
    io_lock = threading.Lock()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f, requests.Session() as session:
        # Default adapter pool caps at 10 connections; size it to CONCURRENCY
        # so raising CONCURRENCY doesn't trigger "Connection pool is full"
        # warnings (requests would still work, just with extra contention).
        adapter = requests.adapters.HTTPAdapter(pool_connections=CONCURRENCY, pool_maxsize=CONCURRENCY)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        f.flush()

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [pool.submit(send_one, session, i) for i in range(1, NUM_REQUESTS + 1)]

            for future in as_completed(futures):
                row = future.result()

                with io_lock:
                    completed += 1
                    writer.writerow(row)
                    f.flush()

                    if row["status"] == "ok":
                        ok_count += 1
                        if row["prompt_tokens"] != "":
                            prompt_tokens_seen.add(row["prompt_tokens"])
                        if row["completion_tokens"] != "":
                            total_completion_tokens += row["completion_tokens"]
                        if row["total_tokens"] != "":
                            total_tokens_sum += row["total_tokens"]
                        latencies.append(row["latency_ms"])

                        print(
                            f"[{completed:>4}/{NUM_REQUESTS}] OK  (req #{row['index']})  "
                            f"latency={row['latency_ms']:>7.1f}ms  "
                            f"prompt_tokens={row['prompt_tokens']:<5} "
                            f"completion_tokens={row['completion_tokens']:<5} "
                            f"total_tokens={row['total_tokens']:<5}"
                        )
                        print(f"           input : {row['input']}")
                        print(f"           output: {row['output']!r}")
                    else:
                        err_count += 1
                        print(
                            f"[{completed:>4}/{NUM_REQUESTS}] FAIL (req #{row['index']})  "
                            f"http_status={row['http_status']} error={row['error']}"
                        )

    run_end = datetime.now(timezone.utc)
    duration_s = (run_end - run_start).total_seconds()

    print("=" * 78)
    print("Run complete")
    print(f"  end time         : {run_end.isoformat(timespec='seconds')}")
    print(f"  total duration   : {duration_s:.1f}s")
    print(f"  successes        : {ok_count}/{NUM_REQUESTS}")
    print(f"  failures         : {err_count}/{NUM_REQUESTS}")
    if prompt_tokens_seen:
        consistent = "yes" if len(prompt_tokens_seen) == 1 else "no"
        print(f"  prompt_tokens consistent across calls : {consistent} (values seen: {sorted(prompt_tokens_seen)})")
    if latencies:
        print(f"  avg latency      : {sum(latencies) / len(latencies):.1f}ms")
        print(f"  min/max latency  : {min(latencies):.1f}ms / {max(latencies):.1f}ms")
    if ok_count:
        print(f"  avg completion_tokens : {total_completion_tokens / ok_count:.1f}")
        print(f"  total tokens (all calls) : {total_tokens_sum}")
    print(f"  results saved to : {OUTPUT_CSV}")
    print("=" * 78)


if __name__ == "__main__":
    main()
