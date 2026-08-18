# LLM Load Test — Script vs. Grafana Deviation Report

> **Target:** `dev.ai4inclusion.org`, model `llm/bharathi`
> **Method:** 500 identical OpenAI-compatible chat-completions requests per run, concurrency = 10
> **Runs:** two, at different fixed prompt-token sizes, to see whether the Grafana/true gap holds
> steady or scales with payload size.

---

## Run 1 — 26-token input

> Script: `scripts/llm-load-test.py` · Input: fixed 79-char prompt
> Result: 500/500 successful, total duration 372.5s

| Metric | True value (script/CSV) | Grafana | Deviation | Grafana vs. true |
|---|---|---|---|---|
| Median latency | 7.533 s | 6.57 s | **−12.8%** | underreports |
| Median prompt tokens | 26 | 30 | **+15.4%** | overreports |
| Request count | 500 | 508 | **+1.6%** | overreports |

### Notes

- **Latency**: The script's console summary reports *mean* latency (7663.3 ms), not median — the
  7.533s median above was recomputed directly from the raw per-request CSV so it's a like-for-like
  comparison against Grafana's median. Grafana reads ~12.8% low, plausible if its latency metric is
  captured at a different point in the request path (e.g. excludes proxy/network overhead the
  client-side script measures) or its bucketing/percentile approximation smooths outliers — the
  true run had a wide spread (5.834s–17.571s).
- **Prompt tokens**: Ground truth is a hard constant — 26 tokens on all 500 calls, since the same
  input was sent every time. Grafana's 30 is therefore a genuine +15.4% overcount, not a percentile
  artifact (there's no real variance to produce a different median).
- **Request count**: 508 vs. actual 500 is a modest +1.6% overcount — could be retries,
  health-checks, or other traffic captured in the same Grafana window that isn't isolated to this
  test run.

---

## Run 2 — 557-token input

> Script: `scripts/llm-load-test-100-110-tokens.py` (input lengthened past its original name)
> Input: fixed ~479-word prompt, measured at 557 prompt tokens on every call
> Result: 500/500 successful, total duration 1082.6s

| Metric | True value (script/CSV) | Grafana | Deviation | Grafana vs. true |
|---|---|---|---|---|
| Median latency | 21.980 s | 10 s | **−54.5%** | underreports |
| Median prompt tokens | 557 | 750 | **+34.6%** | overreports |
| Request count | 500 | 505 | **+1.0%** | overreports |

*Deviation = (Grafana − True) / True × 100, for both runs.*

### Notes

- **Latency**: Same mean-vs-median caveat as Run 1 — the script's own summary printed a 22009.7 ms
  *mean*; the 21.980s figure above is the true median from the raw CSV. The underreport here
  (−54.5%) is far larger than Run 1's (−12.8%), which is the most notable finding of this report:
  the gap **grows with request duration/payload size** rather than staying constant. That points
  away from a fixed measurement offset and toward Grafana's latency metric missing a
  duration-dependent portion of the request — e.g. only capturing time-to-first-token or a fixed
  early span of the response instead of the full generation time, which matters far more once
  completions run to 400+ tokens (avg completion here: 435.5 tokens vs. ~152 in Run 1).
- **Prompt tokens**: Ground truth is again a hard constant (557 on all 500 calls). The absolute
  overcount jumped from +4 tokens (Run 1) to +193 tokens (Run 2), and the percentage overcount
  nearly doubled (+15.4% → +34.6%). The ratio of reported-to-true also shifted (1.15× → 1.35×), so
  this isn't a simple fixed additive or fixed multiplicative bias — with only two data points it's
  not possible to fit the exact relationship, but the error is clearly **not constant** and grows
  faster than the prompt itself. Worth a third run at a different token size to see whether the
  ratio keeps climbing or levels off.
- **Request count**: 505 vs. actual 500 (+1.0%) is consistent with Run 1's small, likely
  background-traffic overcount (+1.6%) — this metric looks stable across runs and is the least
  concerning of the three.
- **Total tokens — median vs. mean (internal check, no Grafana figure)**: true median total tokens
  = **994**, true mean total tokens = **992.544** (496,272 summed total ÷ 500 requests) — a gap of
  only **−0.15%** ((mean − median) / median × 100). Verified directly against the raw CSV, including
  a per-row check that `prompt_tokens + completion_tokens == total_tokens` on all 500 rows (zero
  mismatches). Median and mean landing this close means the total-token distribution is tight and
  symmetric, unlike latency, which had a wide 16.7s–33.2s spread on the same run. Since
  `prompt_tokens` is fixed at 557 for every call, essentially all of that (negligible) spread comes
  from `completion_tokens` varying modestly around its ~435-437 average/median — token *count*
  variance is not what's driving the latency variance seen in this run; generation speed is.

---

## Cross-Run Summary

| Metric | Run 1 (26 tokens) | Run 2 (557 tokens) | Trend |
|---|---|---|---|
| Latency deviation | −12.8% | −54.5% | **Worsens sharply** as request duration grows |
| Prompt-token deviation | +15.4% | +34.6% | **Worsens** as payload size grows |
| Request-count deviation | +1.6% | +1.0% | Stable, roughly within noise |

## Takeaway

Grafana's numbers aren't just off by a constant margin — the deviation **scales with payload size**
for both latency and token accounting. At small payloads (26 tokens, ~7.5s requests) the gaps were
tolerable (−13% / +15%); at larger payloads (557 tokens, ~22s requests) they became severe (−55% /
+35%). Request-count tracking is the one metric that stayed reliable across both runs. Given this
trend, Grafana's latency and token dashboards should not be trusted for capacity planning or SLA
reporting on longer-running LLM requests until the underlying metric collection is investigated —
the true numbers from direct client measurement are the only reliable source at this scale.

---

## Raw Data

- Run 1: `scripts/llm-load-test-results.csv` (500 rows)
- Run 2: `scripts/llm-load-test-500-plus-tokens-results.csv` (500 rows)

Each file: input, output, prompt/completion/total tokens, latency, timestamp per call.
