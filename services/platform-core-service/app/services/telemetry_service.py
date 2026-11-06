"""Business logic for querying and processing telemetry traces from OpenSearch."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, status

from app.utils.opensearch_client import OpenSearchTraceClient

SORT_FIELD_MAP = {
    "timestamp": "@timestamp",
    "url": "attributes.url.keyword",
    "latency": "attributes.total_time_ms",
    "status_code": "attributes.status_code",
}

logger = logging.getLogger(__name__)

_TRACE_ID_KEYWORD = "context.trace_id.keyword"
_TRACE_ID_FIELD = "context.trace_id"
_TIMESTAMP_FIELD = "@timestamp"

# Fixed display order for the trace-detail waterfall: every task type
# (LLM, NMT, ASR, ...) resolves a model before calling it, so this sequence
# is always correct regardless of task type or nesting shape.
_SPAN_ORDER = {"request": 0, "model": 1, "ai-inference": 2}

# Safety cap on how many matching trace_ids we'll enumerate to build the
# by_level/by_task breakdown. Keeps a very large filtered result set from
# generating an unbounded number of OpenSearch round trips; total (used by
# the pagination footer and the Total Requests card) is unaffected by this
# cap since it comes from a single cardinality aggregation. Above this cap,
# composite aggregation buckets come back in ascending lexicographic order
# of trace_id (not recency), so the covered slice is an arbitrary sample,
# not "the most recent N" - callers must treat by_level/by_task as partial
# when aggregations.partial is set.
_MAX_BREAKDOWN_TRACE_IDS = 20000

# Cap the cardinality aggregation's exactness to the same bound as the
# breakdown enumeration above, so `total` (the pagination/Total Requests
# figure) and sum(by_level.values()) (an exact enumeration) can't silently
# disagree within that range. Without this, OpenSearch's cardinality agg is
# only exact up to its default precision_threshold (3000) and falls back to
# an approximate HyperLogLog++ estimate beyond it - which would drift from
# the exact breakdown count at the ticket's own reported scale (11,401).
_TOTAL_PRECISION_THRESHOLD = min(_MAX_BREAKDOWN_TRACE_IDS, 40000)  # 40000 is OpenSearch's own hard ceiling

# OpenSearch's dynamic mapping gives each string attribute a `.keyword`
# subfield that only indexes values up to this length.
_KEYWORD_IGNORE_ABOVE = 256

# Spans-per-trace ceiling used when sizing Step 3's per-page span fetch below.
# Keeps page_size * this under OpenSearch's default 10k result-window limit.
_SPAN_CEILING_PER_TRACE = 50
_NULL_TRACE_ID = "0x" + "0" * 32

# The breakdown's own, tighter per-trace span ceiling (vs. Step 3's 50 above).
# ~3 spans/trace has been observed in this index; 15 keeps a 5x margin over
# that while allowing much bigger batches - and therefore far fewer
# OpenSearch round trips - than reusing Step 3's more conservative ceiling
# would (10000 // 15 = 666 trace_ids per batch, vs 10000 // 50 = 200).
_BREAKDOWN_SPAN_CEILING_PER_TRACE = 15
_BREAKDOWN_BATCH_SIZE = max(1, 10000 // _BREAKDOWN_SPAN_CEILING_PER_TRACE)

# How many of those batch fetches run at once. Each is a blocking OpenSearch
# call offloaded to a worker thread (see _compute_full_breakdown), so this
# bounds how many worker threads - and how much concurrent load on the
# OpenSearch cluster - one dashboard request can use at a time.
_BREAKDOWN_CONCURRENCY = 5

# AC-17: keyword searches matching more than this many traces return 400.
# _collect_all_trace_ids is called with limit=_MAX_KEYWORD_TRACE_IDS + 1; if it
# returns more than _MAX_KEYWORD_TRACE_IDS IDs the caller must narrow their search.
_MAX_KEYWORD_TRACE_IDS = 20000


def _collect_all_trace_ids(opensearch_client: OpenSearchTraceClient, filter_query: dict, limit: int) -> list:
    """Get the ID of every log that matches the current filters - not just one page's worth.

    OpenSearch refuses to return more than 10,000 results in a single request,
    so this asks for results in batches (a "composite" aggregation, which comes
    with a bookmark called `after_key`) and keeps asking for the next batch
    until either every matching trace_id has been collected or `limit` is
    reached. `limit` exists so a filter that matches an extreme number of
    traces can't turn into an unbounded number of requests.

    Raises RuntimeError if a page comes back without an "aggregations" key,
    which signals the query itself failed (rejected/malformed query, cluster
    error, etc - `OpenSearchTraceClient.search_traces` swallows the real
    exception and returns a bare hits-only dict with no "aggregations" key
    at all). Treating that missing key the same as "no more matching traces"
    is what silently produced Success: 0 / Failures: 0 next to a correct
    Total earlier in this fix's history (a rejected aggregation query looks
    identical to "search finished" unless this is checked explicitly) - so
    this fails loudly instead of guessing.
    """
    trace_ids = []
    after_key = None

    while len(trace_ids) < limit:
        composite = {
            "size": min(10000, limit - len(trace_ids)),
            "sources": [{"trace_id": {"terms": {"field": _TRACE_ID_KEYWORD}}}],
        }
        if after_key:
            composite["after"] = after_key

        response = opensearch_client.search_traces(
            query=filter_query,
            size=0,
            aggs={"trace_ids": {"composite": composite}},
        )

        if "aggregations" not in response:
            raise RuntimeError(
                "OpenSearch composite aggregation for trace enumeration returned no "
                "aggregations - the query likely failed; see server logs for the underlying error."
            )

        trace_ids_agg = response["aggregations"].get("trace_ids", {})
        buckets = trace_ids_agg.get("buckets", [])
        if not buckets:
            break

        trace_ids.extend(bucket["key"]["trace_id"] for bucket in buckets)

        after_key = trace_ids_agg.get("after_key")
        if not after_key:
            break

    return trace_ids


def _exact_attribute_match(attribute: str, value: str) -> dict:
    """Exact-value, case-insensitive filter on one span attribute.

    `term` on the `.keyword` subfield, because match_phrase on the analysed
    text field would also match longer values containing the same tokens
    (user=customer-1 would find customer-1-admin). Values longer than the
    keyword cap aren't in `.keyword` at all, so those fall back to match_phrase.
    case_insensitive keeps both branches consistent: the analysed field that
    match_phrase reads is already lowercased, so `Shesna` is found by `shesna`
    either way.
    """
    field = f"attributes.{attribute}"
    if len(value) > _KEYWORD_IGNORE_ABOVE:
        return {"match_phrase": {field: value}}
    return {"term": {f"{field}.keyword": {"value": value, "case_insensitive": True}}}


def _escape_wildcard(value: str) -> str:
    """Escape OpenSearch wildcard special characters in user-supplied input."""
    return value.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _contains_field_match(field: str, value: str) -> dict:
    """Wildcard contains-match on an arbitrary field (case-insensitive).

    Uses a bool.should combining a wildcard on .keyword (hits docs whose stored
    value is ≤ ignore_above) and a match_phrase on the text field (hits docs
    whose stored value exceeds ignore_above and was never written to .keyword).
    """
    if len(value) > _KEYWORD_IGNORE_ABOVE:
        return {"match_phrase": {field: value}}
    return {
        "bool": {
            "should": [
                {"wildcard": {f"{field}.keyword": {"value": f"*{_escape_wildcard(value)}*", "case_insensitive": True}}},
                {"match_phrase": {field: value}},
            ],
            "minimum_should_match": 1,
        }
    }


def _contains_attribute_match(attribute: str, value: str) -> dict:
    """Wildcard contains-match on one span attribute (case-insensitive)."""
    return _contains_field_match(f"attributes.{attribute}", value)


def _metadata_kv_match(key: str, value: str) -> dict:
    """Match a `metadata_kv` entry by exact key and contains-match on the value.

    metadata_kv stores "key=value" strings for arbitrary caller-supplied
    metadata, so a plain contains-match on the composite string (e.g.
    "*env=prod*") would also match an unrelated key like "dev_env=prod-2",
    since that substring appears inside it too. Anchoring the wildcard to
    start with "key=" keeps the key exact while still allowing a
    substring match on the value, per the documented filter contract.
    """
    field = "attributes.metadata_kv"
    composite = f"{key}={value}"
    if len(composite) > _KEYWORD_IGNORE_ABOVE:
        return {"match_phrase": {field: composite}}
    return {
        "wildcard": {
            f"{field}.keyword": {
                "value": f"{_escape_wildcard(key)}=*{_escape_wildcard(value)}*",
                "case_insensitive": True,
            }
        }
    }


# Maps span name → {entry_key: attribute_key}.
# Single source of truth for which fields live exclusively on which span type.
# _apply_span_to_trace reads this for trace assembly; _span_owner reads it for
# cross-span filter conflict detection. Add new span-exclusive fields here only.
_SPAN_FIELD_MAP: dict[str, dict[str, str]] = {
    "model":   {"task_type": "task_type",    "model_name": "model_name"},
    "request": {"url":       "url",           "latency":    "total_time_ms",
                "status_code": "status_code", "method":     "method",
                "metadata":  "metadata_kv"},
}

# end_user / app_id aren't span-exclusive: the request span normally carries
# them, but multipart audio routes (proxy_multipart) open no request span, so
# the model span is the only one that has them. Handled outside
# _SPAN_FIELD_MAP so request stays authoritative while still falling back to
# whichever span actually carries the value.
_FALLBACK_SPAN_FIELDS: dict[str, str] = {"app_id": "app_id", "end_user": "enduser.id"}


def _span_owner(entry_key: str) -> Optional[str]:
    """Return the span type that exclusively carries this field, or None if shared."""
    for span_name, fields in _SPAN_FIELD_MAP.items():
        if entry_key in fields:
            return span_name
    return None


def _apply_span_to_trace(entry: dict, span_name: str, attrs: dict) -> None:
    for entry_key, attr_key in _SPAN_FIELD_MAP.get(span_name, {}).items():
        if not entry.get(entry_key):
            value = attrs.get(attr_key)
            if entry_key == "task_type" and value:
                value = value.upper()
            entry[entry_key] = value
    # Extract status: the request span is authoritative for the overall trace
    # outcome — it reflects the HTTP response and is always present. Always
    # override with its status so a model span arriving earlier in the sorted
    # hits cannot mask a request-level failure with its own success status.
    # For other spans, only fill in if we have nothing yet.
    span_status = attrs.get("status")
    if span_status and (span_name == "request" or not entry["status"]):
        entry["status"] = span_status

    # app_id / end_user: same request-is-authoritative-but-fall-back-if-absent
    # rule as status, since proxy_multipart's model span is the only span
    # carrying them when there's no request span to override from.
    for entry_key, attr_key in _FALLBACK_SPAN_FIELDS.items():
        value = attrs.get(attr_key)
        if value and (span_name == "request" or not entry.get(entry_key)):
            entry[entry_key] = value


def _new_trace_entry(trace_id: str, source: dict, attrs: dict, tenant_filter: Optional[str]) -> dict:
    return {
        "trace_id":    trace_id,
        "service":     source.get("service_name"),
        "task_type":   None,
        "status":      None,
        "url":         None,
        "latency":     None,
        "status_code": None,
        "tenant_id":   tenant_filter or attrs.get("tenantId"),
        "timestamp":   source.get(_TIMESTAMP_FIELD) or source.get("timestamp"),
        "method":      None,
        "error":       None,
        "model_name":  None,
        "app_id":      None,
        "end_user":    None,
        "metadata":    None,
    }


def _build_traces_map(hits: list, tenant_filter: Optional[str]) -> dict:
    """Turn a list of raw span records into one summary record per trace (log).

    A single log is made up of several spans (request, model, ai-inference),
    each carrying different pieces of information: task_type lives on the
    'model' span, url lives on the 'request' span, and status lives on the
    'request' span. Each trace has exactly one request span (the gateway
    issues one trace ID per HTTP request), so status is unambiguously
    single-valued per trace.

    This function is shared by the page-data path and `_compute_full_breakdown`
    so both use the same extraction rule.
    """
    traces_map = {}
    for hit in hits:
        source = hit.get("_source", {})
        trace_id = source.get("context", {}).get("trace_id")
        if not trace_id:
            continue

        span_name = source.get("name")
        attrs = source.get("attributes", {})

        if trace_id not in traces_map:
            traces_map[trace_id] = _new_trace_entry(trace_id, source, attrs, tenant_filter)
        elif source.get("service_name") and not traces_map[trace_id]["service"]:
            traces_map[trace_id]["service"] = source.get("service_name")

        _apply_span_to_trace(traces_map[trace_id], span_name, attrs)
        # Request span is authoritative for timestamp (same as status); override
        # whatever the first-seen span set so sort-by-timestamp is consistent.
        if span_name == "request":
            traces_map[trace_id]["timestamp"] = (
                source.get(_TIMESTAMP_FIELD) or source.get("timestamp") or traces_map[trace_id]["timestamp"]
            )
            # error comes from status.description, not span attributes
            if traces_map[trace_id]["error"] is None:
                traces_map[trace_id]["error"] = source.get("status", {}).get("description")

    return traces_map


# Maps selected_column key → (row key, base key). Columns with special logic
# (error, status) are handled explicitly in _build_row.
_COLUMN_TO_FIELD: dict[str, tuple[str, str]] = {
    "timestamp":   ("timestamp",   "timestamp"),
    "task_type":   ("task_type",   "task_type"),
    "url":         ("url",         "url"),
    "institution": ("tenant_id",   "tenant_id"),
    "service":     ("service",     "service"),
    "status_code": ("status_code", "status_code"),
    "latency":     ("latency",     "latency"),
    "method":      ("method",      "method"),
    "model":       ("model",       "model_name"),
    "application": ("application", "app_id"),
    "end_user":    ("end_user",    "end_user"),
    "metadata":    ("metadata",    "metadata"),
}


def _build_row(tid: str, base: dict, selected_columns: frozenset, is_admin: bool) -> dict:
    row: dict = {"trace_id": tid}
    for col in selected_columns:
        if col == "error":
            row["error"] = base.get("error") if is_admin else None
        elif col == "status":
            row["status"] = base.get("status", "unknown")
        elif col in _COLUMN_TO_FIELD:
            row_key, base_key = _COLUMN_TO_FIELD[col]
            row[row_key] = base.get(base_key)
    return row


def _build_page_data(
    traces_map: dict,
    selected_columns: frozenset,
    paginated_trace_ids: list,
    *,
    is_admin: bool = False,
) -> list:
    """Build response rows containing only the selected columns.

    trace_id is always included as the row identifier regardless of selection.
    All span fields are already merged into traces_map by _build_traces_map,
    so a single loop over paginated_trace_ids is sufficient.
    """
    result = []
    for tid in paginated_trace_ids:
        if tid not in traces_map:
            continue
        result.append(_build_row(tid, traces_map[tid], selected_columns, is_admin))
    return result


async def _compute_full_breakdown(opensearch_client: OpenSearchTraceClient, trace_ids: list, tenant_filter: Optional[str]) -> tuple:
    """Count success/failure and task_type across ALL matching logs - not just the page.

    This is what the "Success" and "Failures" summary cards are built from.
    It takes the full list of trace_ids (from _collect_all_trace_ids), fetches
    their spans in batches of _BREAKDOWN_BATCH_SIZE, and reduces each batch
    with _build_traces_map so every trace resolves to exactly one status and
    one task_type before it's tallied. Tallying after that per-trace
    reduction - instead of a raw OpenSearch aggregation over span documents -
    is what guarantees Success + Failures always adds up to Total: a trace
    can't get counted twice just because two of its spans disagree.

    Each batch re-fetches its trace_ids' spans unfiltered by the original
    query filters (same as Step 3 already does for the page), rather than
    reusing whatever documents happened to satisfy those filters. This
    matters concretely: a `task_types` filter only matches the 'model'/
    'ai-inference' spans (they're the only spans carrying attributes.task_type)
    - the 'request' span, which carries attributes.status, never matches
    that filter at all. An earlier version of this function tried folding
    classification directly into the filtered enumeration query via a
    top_hits sub-aggregation to cut down on round trips, and it was verified
    against live data (task_types filter active, exactly this ticket's own
    repro) to silently miscount a Failure trace as Success, because the
    'request' span carrying its real status was outside that filtered
    aggregation's document set entirely - not just outside the top_hits
    window size. This function fetches by trace_id only, with no filter
    reuse, specifically to avoid that.

    Batches run concurrently (bounded by _BREAKDOWN_CONCURRENCY, via
    asyncio.to_thread) instead of one after another. `opensearch_client`'s
    underlying HTTP client is synchronous, so a naive sequential loop here
    blocks this async request handler's event loop for the entire fan-out -
    at the ticket's reported scale of 11,401 traces that was ~58 sequential
    blocking calls with _SPAN_CEILING_PER_TRACE's batch size; at
    _BREAKDOWN_BATCH_SIZE it's ~18 calls, and running them concurrently
    keeps the event loop free to serve other requests while they're in
    flight instead of stalling on them one at a time.

    Each batch's fetch is capped at len(batch) * _BREAKDOWN_SPAN_CEILING_PER_TRACE
    spans total (not per trace_id), sorted newest-first, so if the batch's
    real span count exceeds that cap, the oldest trace_ids in it can end up
    with zero spans in the response and silently drop out of the tally -
    while other, newer trace_ids in the same batch still return spans
    normally, so the response is never a fully-empty `hits` list a simple
    zero-hits check could catch. This is detected by comparing which
    trace_ids the batch actually classified against which it was asked
    about; a mismatch flips the returned `truncated` flag so the caller can
    mark the response `partial` instead of presenting an undercount as exact.

    Returns (by_level, by_task, truncated, all_traces).
    """
    if not trace_ids:
        return {}, {}, False, {}

    by_level = {}
    by_task = {}
    all_traces: dict = {}
    truncated = False
    semaphore = asyncio.Semaphore(_BREAKDOWN_CONCURRENCY)
    batches = [trace_ids[i:i + _BREAKDOWN_BATCH_SIZE] for i in range(0, len(trace_ids), _BREAKDOWN_BATCH_SIZE)]

    async def fetch_batch(batch: list) -> dict:
        trace_id_clauses = [{"match_phrase": {_TRACE_ID_FIELD: tid}} for tid in batch]
        async with semaphore:
            return await asyncio.to_thread(
                opensearch_client.search_traces,
                query={"bool": {"should": trace_id_clauses, "minimum_should_match": 1}},
                size=len(batch) * _BREAKDOWN_SPAN_CEILING_PER_TRACE,
                source_fields=[_TIMESTAMP_FIELD, "name", _TRACE_ID_FIELD, "attributes", "service_name"],
            )

    responses = await asyncio.gather(*(fetch_batch(batch) for batch in batches))

    for batch, response in zip(batches, responses):
        hits = response.get("hits", {}).get("hits", [])
        batch_traces = _build_traces_map(hits, tenant_filter)
        all_traces.update(batch_traces)

        # Every trace_id in `batch` was just enumerated as matching the filters, so
        # any of them missing from batch_traces means the fetch above didn't return
        # a span for it - either OpenSearch failed silently for the whole batch (a
        # plain search response has no structural "it failed" signal, unlike the
        # aggregations-key check in _collect_all_trace_ids), or the batch's total
        # span count exceeded its size cap and pushed this trace_id's spans out of
        # the sorted window. Either way, by_level/by_task undercounts these traces.
        missing = set(batch) - set(batch_traces.keys())
        if missing:
            truncated = True
            logger.warning(
                f"Trace breakdown batch dropped {len(missing)} of {len(batch)} trace_ids "
                "(zero spans returned for them); by_level/by_task will undercount - "
                "marking this response partial."
            )

        for trace in batch_traces.values():
            status_key = trace.get("status") or "unknown"
            task_key = (trace.get("task_type") or "unknown").upper()
            by_level[status_key] = by_level.get(status_key, 0) + 1
            by_task[task_key] = by_task.get(task_key, 0) + 1

    return by_level, by_task, truncated, all_traces


def _build_base_filter_clauses(
    tenant_filter: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> list:
    base_filter_clauses = []
    if tenant_filter:
        base_filter_clauses.append({"match_phrase": {"attributes.tenantId": tenant_filter}})
    if start_date or end_date:
        range_query: dict = {}
        if start_date:
            range_query["gte"] = start_date
        if end_date:
            range_query["lte"] = end_date
        base_filter_clauses.append({"range": {_TIMESTAMP_FIELD: range_query}})
    return base_filter_clauses


def _run_keyword_prequery(
    opensearch_client: OpenSearchTraceClient,
    q: Optional[str],
    base_filter_clauses: list,
) -> Optional[list]:
    if not q:
        return None
    pre_query: dict = {
        "bool": {
            "filter": base_filter_clauses,
            "must": [{"multi_match": {"query": q, "fields": ["*"], "type": "phrase", "lenient": True}}],
        }
    }
    keyword_trace_ids = _collect_all_trace_ids(opensearch_client, pre_query, limit=_MAX_KEYWORD_TRACE_IDS + 1)
    if len(keyword_trace_ids) > _MAX_KEYWORD_TRACE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many results. Please narrow your date range or refine your search.",
        )
    return keyword_trace_ids


def _intersect_trace_id_gates(a: Optional[list], b: Optional[list]) -> Optional[list]:
    """Intersect two optional trace-ID gate lists.
    None means no gate (all traces pass); empty list means nothing matched."""
    if a is None:
        return b
    if b is None:
        return a
    b_set = set(b)
    return [x for x in a if x in b_set]


def _resolve_cross_span_filters(
    opensearch_client: OpenSearchTraceClient,
    base_filter_clauses: list,
    span_groups: dict,
) -> Optional[list]:
    """Resolve a cross-span conflict into a trace-ID intersection.

    span_groups comes from _build_search_filter_clauses: span_owner → [(attr, value)].
    Runs pre-queries in selectivity order (non-request groups first) and cascades
    each group's result IDs into the next pre-query, so a broad group like method=POST
    is narrowed by prior selective groups before it is evaluated.
    Returns None when there is no conflict (single or empty span_groups).
    """
    if len(span_groups) <= 1:
        return None

    # Non-request groups (model, url, …) are typically selective; run them first
    # so their IDs gate the broader request-span group (method=POST matches everything).
    ordered = sorted(span_groups.items(), key=lambda kv: 0 if kv[0] != "request" else 1)

    gating: Optional[list] = None
    for span_name, filters in ordered:
        anchor = [{"term": {"name": span_name}}] if span_name == "request" else []
        # Inject accumulated gate to narrow this pre-query; skip injection when the
        # gate is too large to use as a terms clause efficiently.
        gate_clause = (
            [{"terms": {_TRACE_ID_KEYWORD: gating}}]
            if gating is not None and len(gating) <= _MAX_KEYWORD_TRACE_IDS
            else []
        )
        clauses = base_filter_clauses + anchor + gate_clause + [
            _contains_attribute_match(attr, val) for attr, val in filters
        ]
        ids = _collect_all_trace_ids(
            opensearch_client, {"bool": {"filter": clauses}}, limit=_MAX_KEYWORD_TRACE_IDS + 1
        )
        gating = _intersect_trace_id_gates(gating, ids)
        if gating is not None and len(gating) == 0:
            return gating

    if gating is not None and len(gating) > _MAX_KEYWORD_TRACE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many results. Please narrow your date range or refine your search.",
        )
    return gating


def _build_task_type_clauses(task_types: str) -> list:
    types_list = [t.strip() for t in task_types.split(",") if t.strip()]
    if len(types_list) == 1:
        return [{"match_phrase": {"attributes.task_type": types_list[0]}}]
    if types_list:
        return [{"bool": {"should": [{"match_phrase": {"attributes.task_type": t}} for t in types_list], "minimum_should_match": 1}}]
    return []


def _categorize_filter(attr_name: str, value: str, filter_clauses: list, span_groups: dict) -> None:
    owner = _span_owner(attr_name)
    if owner:
        span_groups.setdefault(owner, []).append((attr_name, value))
    else:
        filter_clauses.append(_exact_attribute_match(attr_name, value))


@dataclass
class _SpanFilterParams:
    method: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    service: Optional[str] = None
    url: Optional[str] = None
    application: Optional[str] = None


def _build_search_filter_clauses(
    base_filter_clauses: list,
    task_types: Optional[str],
    effective_status: Optional[str],
    user: Optional[str],
    metadata_key: Optional[str],
    metadata_value: Optional[str],
    service_id: Optional[str],
    status_code_list: list,
    needs_request_anchor: bool,
    keyword_trace_ids: Optional[list],
    span_filters: Optional[_SpanFilterParams] = None,
) -> tuple[list, dict]:
    """Returns (filter_clauses, span_groups).

    span_groups maps span_owner → [(attr_name, value)] for filters whose attributes
    are exclusive to one span type (per _SPAN_FIELD_MAP). When span_groups has more
    than one key, the caller must resolve the cross-span conflict via pre-queries
    rather than ANDing the filters in a single bool.must.
    """
    filter_clauses = list(base_filter_clauses)
    span_groups: dict[str, list] = {}
    sf = span_filters or _SpanFilterParams()

    if task_types:
        filter_clauses.extend(_build_task_type_clauses(task_types))
    if effective_status:
        filter_clauses.append({"match_phrase": {"attributes.status": effective_status}})
    if user is not None:
        filter_clauses.append(_contains_attribute_match("enduser.id", user))
    if metadata_key is not None:
        filter_clauses.append(_metadata_kv_match(metadata_key, metadata_value))
    if service_id:
        filter_clauses.append(_exact_attribute_match("service_id", service_id))
    if status_code_list:
        filter_clauses.append({"terms": {"attributes.status_code": status_code_list}})
    if sf.method:
        _categorize_filter("method", sf.method, filter_clauses, span_groups)
    if sf.model:
        _categorize_filter("model_name", sf.model, filter_clauses, span_groups)
    if sf.url:
        _categorize_filter("url", sf.url, filter_clauses, span_groups)
    if sf.application:
        filter_clauses.append(_contains_attribute_match("app_id", sf.application))
    if sf.error:
        filter_clauses.append(_contains_field_match("status.description", sf.error))
    if sf.service:
        filter_clauses.append({"match_phrase": {"service_name": sf.service}})
    if needs_request_anchor:
        filter_clauses.append({"term": {"name": "request"}})
    if keyword_trace_ids is not None:
        filter_clauses.append({"terms": {_TRACE_ID_KEYWORD: keyword_trace_ids}})
    return filter_clauses, span_groups


def _extract_paginated_trace_ids(ids_response: dict) -> list:
    paginated_trace_ids = []
    for hit in ids_response.get("hits", {}).get("hits", []):
        trace_id = hit.get("_source", {}).get("context", {}).get("trace_id")
        if trace_id and trace_id != _NULL_TRACE_ID and trace_id not in paginated_trace_ids:
            paginated_trace_ids.append(trace_id)
    return paginated_trace_ids


def _paginate_resolved_traces(
    all_traces: dict,
    status: str,
    sort_by: Optional[str],
    sort_dir: str,
    offset: int,
    page_size: int,
) -> list:
    """Filter all_traces to resolved status, sort, and return one page of trace IDs."""
    matched = [(tid, t) for tid, t in all_traces.items() if (t.get("status") or "unknown") == status]
    sort_attr = sort_by if sort_by in SORT_FIELD_MAP else "timestamp"
    reverse = (sort_dir == "desc")

    def _key(item: tuple) -> tuple:
        val = item[1].get(sort_attr)
        if val is None:
            return (1, 0.0, "")
        if isinstance(val, (int, float)):
            return (0, float(val), "")
        return (0, 0.0, str(val))

    matched.sort(key=_key, reverse=reverse)
    return [tid for tid, _ in matched[offset: offset + page_size]]


def _fetch_span_page_data(
    opensearch_client: OpenSearchTraceClient,
    paginated_trace_ids: list,
    selected_columns: frozenset,
    tenant_filter: Optional[str],
    is_admin: bool,
) -> tuple:
    if not paginated_trace_ids:
        return [], paginated_trace_ids
    trace_id_clauses = [{"match_phrase": {_TRACE_ID_FIELD: tid}} for tid in paginated_trace_ids]
    step3_query: dict = {"bool": {"should": trace_id_clauses, "minimum_should_match": 1}}
    spans_response = opensearch_client.search_traces(
        query=step3_query,
        size=len(paginated_trace_ids) * _SPAN_CEILING_PER_TRACE,
        source_fields=[_TIMESTAMP_FIELD, "name", _TRACE_ID_FIELD, "attributes", "service_name", "status"],
    )
    hits = spans_response.get("hits", {}).get("hits", [])
    traces_map = _build_traces_map(hits, tenant_filter)
    data = _build_page_data(traces_map, selected_columns, paginated_trace_ids, is_admin=is_admin)
    return data, paginated_trace_ids


def _resolve_paginated_ids_for_status(
    opensearch_client: OpenSearchTraceClient,
    is_partial: bool,
    all_traces: dict,
    by_level: dict,
    effective_status: str,
    filter_query: dict,
    page_size: int,
    offset: int,
    sort_clause: list,
    sort_by: Optional[str],
    sort_dir: str,
) -> tuple:
    """Return (total, paginated_trace_ids) for a status-filtered search.

    When the breakdown was capped (is_partial=True), falls back to span-level
    collapse so the page remains time-ordered.
    """
    if is_partial:
        ids_response = opensearch_client.search_traces(
            query=filter_query,
            size=page_size,
            from_=offset,
            source_fields=[_TRACE_ID_FIELD],
            collapse={"field": _TRACE_ID_KEYWORD},
            sort=sort_clause,
            aggs={"trace_count": {"cardinality": {
                "field": _TRACE_ID_KEYWORD,
                "precision_threshold": _TOTAL_PRECISION_THRESHOLD,
            }}},
        )
        total = ids_response.get("aggregations", {}).get("trace_count", {}).get("value", 0)
        paginated_trace_ids = _extract_paginated_trace_ids(ids_response)
    else:
        total = by_level.get(effective_status, 0)
        paginated_trace_ids = _paginate_resolved_traces(
            all_traces, effective_status, sort_by, sort_dir, offset, page_size,
        )
    return total, paginated_trace_ids


async def _compute_agg_totals(
    opensearch_client: OpenSearchTraceClient,
    agg_filter_query: dict,
    effective_status: Optional[str],
    total: int,
    tenant_filter: Optional[str],
) -> tuple:
    if effective_status:
        agg_total_response = opensearch_client.search_traces(
            query=agg_filter_query,
            size=0,
            aggs={"trace_count": {"cardinality": {
                "field": _TRACE_ID_KEYWORD,
                "precision_threshold": _TOTAL_PRECISION_THRESHOLD,
            }}},
        )
        agg_total = agg_total_response.get("aggregations", {}).get("trace_count", {}).get("value", 0)
    else:
        agg_total = total
    is_capped = agg_total > _MAX_BREAKDOWN_TRACE_IDS
    if is_capped:
        logger.warning(
            f"Trace breakdown capped at {_MAX_BREAKDOWN_TRACE_IDS} of {agg_total} matching "
            "traces; by_level/by_task counts are partial for this filter."
        )
    all_trace_ids = _collect_all_trace_ids(opensearch_client, agg_filter_query, min(agg_total, _MAX_BREAKDOWN_TRACE_IDS))
    by_level, by_task, breakdown_truncated, all_traces = await _compute_full_breakdown(opensearch_client, all_trace_ids, tenant_filter)
    is_partial = is_capped or breakdown_truncated
    return agg_total, by_level, by_task, is_partial, all_traces


def _bool_filter(clauses: list) -> dict:
    return {"bool": {"must": clauses}} if clauses else {"match_all": {}}


def _inline_span_filters(span_groups: dict, filter_clauses: list) -> None:
    for filters in span_groups.values():
        for attr, val in filters:
            filter_clauses.append(_contains_attribute_match(attr, val))


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class TraceFilterParams:
    effective_status: Optional[str] = None
    task_types: Optional[str] = None
    user: Optional[str] = None
    metadata_key: Optional[str] = None
    metadata_value: Optional[str] = None
    service_id: Optional[str] = None
    status_code_list: list = field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    q: Optional[str] = None
    method: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    service: Optional[str] = None
    url: Optional[str] = None
    application: Optional[str] = None


@dataclass
class PaginationParams:
    page: int = 1
    page_size: int = 20
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None


async def search_traces(
    opensearch_client: OpenSearchTraceClient,
    *,
    selected_columns: frozenset,
    tenant_filter: Optional[str],
    is_admin: bool,
    filters: TraceFilterParams,
    pagination: PaginationParams,
) -> dict:
    """Execute the full trace search and return a result dict for the route to wrap.

    Returns keys: data, total, agg_total, by_level, by_task, is_partial.
    """
    effective_status = filters.effective_status
    task_types = filters.task_types
    user = filters.user
    metadata_key = filters.metadata_key
    metadata_value = filters.metadata_value
    service_id = filters.service_id
    status_code_list = filters.status_code_list
    start_date = filters.start_date
    end_date = filters.end_date
    q = filters.q
    # Non-admins cannot filter by error: the value is redacted in the response,
    # so accepting the param would let callers recover it by binary-probing.
    error = filters.error if is_admin else None
    method = filters.method
    model = filters.model
    service = filters.service
    url = filters.url
    application = filters.application
    sort_by = pagination.sort_by
    sort_order = pagination.sort_order
    page = pagination.page
    page_size = pagination.page_size

    base_filter_clauses = _build_base_filter_clauses(tenant_filter, start_date, end_date)

    keyword_trace_ids = _run_keyword_prequery(opensearch_client, q, base_filter_clauses)
    if keyword_trace_ids is not None and not keyword_trace_ids:
        return {"data": [], "total": 0, "agg_total": 0, "by_level": {}, "by_task": {}, "is_partial": False}

    needs_request_anchor = bool(
        (status_code_list or sort_by in set(SORT_FIELD_MAP) - {"timestamp"} or error) and not model
    )

    filter_clauses, span_groups = _build_search_filter_clauses(
        base_filter_clauses, task_types, effective_status, user,
        metadata_key, metadata_value, service_id, status_code_list,
        needs_request_anchor, keyword_trace_ids,
        _SpanFilterParams(method=method, model=model, error=error, service=service, url=url, application=application),
    )

    if len(span_groups) <= 1:
        # No cross-span conflict: span-exclusive filters are safe in the main query.
        _inline_span_filters(span_groups, filter_clauses)
    else:
        # Cross-span conflict: resolve each span group via pre-query and intersect.
        cross_span_trace_ids = _resolve_cross_span_filters(opensearch_client, base_filter_clauses, span_groups)
        if cross_span_trace_ids is not None and not cross_span_trace_ids:
            return {"data": [], "total": 0, "agg_total": 0, "by_level": {}, "by_task": {}, "is_partial": False}
        gating_trace_ids = _intersect_trace_id_gates(keyword_trace_ids, cross_span_trace_ids)
        needs_request_anchor = bool(status_code_list or sort_by in set(SORT_FIELD_MAP) - {"timestamp"} or error)
        filter_clauses, _ = _build_search_filter_clauses(
            base_filter_clauses, task_types, effective_status, user,
            metadata_key, metadata_value, service_id, status_code_list,
            needs_request_anchor, gating_trace_ids,
            _SpanFilterParams(error=error, service=service, application=application),
        )

    filter_query = _bool_filter(filter_clauses)
    status_clause = {"match_phrase": {"attributes.status": effective_status}}
    agg_filter_clauses = [c for c in filter_clauses if c != status_clause]
    agg_filter_query = _bool_filter(agg_filter_clauses)

    sort_field = SORT_FIELD_MAP.get(sort_by or "timestamp", _TIMESTAMP_FIELD)
    sort_dir = sort_order if sort_order in {"asc", "desc"} else "desc"
    sort_clause = [{sort_field: {"order": sort_dir}}]

    offset = (page - 1) * page_size

    if effective_status:
        agg_total, by_level, by_task, is_partial, all_traces = await _compute_agg_totals(
            opensearch_client, agg_filter_query, effective_status, 0, tenant_filter,
        )
        total, paginated_trace_ids = _resolve_paginated_ids_for_status(
            opensearch_client, is_partial, all_traces, by_level, effective_status,
            filter_query, page_size, offset, sort_clause, sort_by, sort_dir,
        )
        data, _ = _fetch_span_page_data(
            opensearch_client, paginated_trace_ids, selected_columns, tenant_filter, is_admin,
        )
    else:
        ids_response = opensearch_client.search_traces(
            query=filter_query,
            size=page_size,
            from_=offset,
            source_fields=[_TRACE_ID_FIELD],
            collapse={"field": _TRACE_ID_KEYWORD},
            sort=sort_clause,
            aggs={"trace_count": {"cardinality": {
                "field": _TRACE_ID_KEYWORD,
                "precision_threshold": _TOTAL_PRECISION_THRESHOLD,
            }}},
        )
        total = ids_response.get("aggregations", {}).get("trace_count", {}).get("value", 0)
        paginated_trace_ids = _extract_paginated_trace_ids(ids_response)
        data, _ = _fetch_span_page_data(
            opensearch_client, paginated_trace_ids, selected_columns, tenant_filter, is_admin,
        )
        agg_total, by_level, by_task, is_partial, _ = await _compute_agg_totals(
            opensearch_client, agg_filter_query, effective_status, total, tenant_filter,
        )

    return {
        "data": data,
        "total": total,
        "agg_total": agg_total,
        "by_level": by_level,
        "by_task": by_task,
        "is_partial": is_partial,
    }


def get_trace_spans(
    opensearch_client: OpenSearchTraceClient,
    trace_id: str,
    *,
    is_admin: bool,
    tenant_scope: Optional[str],
) -> tuple:
    """Fetch and transform spans for a single trace.

    Returns (spans, service_name).
    Raises HTTPException(404) if the trace is not found or the caller's tenant
    does not match.
    """
    response = opensearch_client.get_trace_by_id(trace_id, source_fields=[
        _TIMESTAMP_FIELD,
        "name",
        _TRACE_ID_FIELD,
        "context.parent_span_id",
        # span_id too: a failed-over trace has two "model" / "ai-inference"
        # spans, so the UI needs it to tell the rows apart.
        "context.span_id",
        "status",
        "attributes",
        "service_name",
    ])
    hits = response.get("hits", {}).get("hits", [])

    if not hits:
        logger.warning(f"Trace {trace_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )

    # Tenant scoping: a non-admin may only read traces in their own tenant.
    # Return 404 (not 403) so trace existence isn't revealed across tenants.
    # Untenanted traces are treated as not-found for tenant-scoped callers.
    if not is_admin:
        span_tenants = {
            hit.get("_source", {}).get("attributes", {}).get("tenantId")
            for hit in hits
        }
        span_tenants.discard(None)
        if tenant_scope not in span_tenants:
            logger.warning(f"Tenant {tenant_scope} denied access to trace {trace_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace {trace_id} not found",
            )

    spans = []
    service = None
    for hit in hits:
        source = hit.get("_source", {})
        service = service or source.get("service_name")
        spans.append({
            "name": source.get("name"),
            "context": source.get("context", {}),
            "kind": source.get("kind"),
            "attributes": source.get("attributes", {}),
            "timestamp": source.get(_TIMESTAMP_FIELD) or source.get("timestamp"),
        })

    # @timestamp is Fluent Bit's ingestion time, not the span's real OTel
    # end_time (no Time_Key override in fluent-bit.conf), so all spans in a
    # trace land within a few ms of each other regardless of actual duration
    # -- unusable for chronological ordering, and start_time/end_time never
    # reach this index. Every task type follows the same fixed span
    # sequence, so rank by name instead of by (unreliable) time.
    spans.sort(key=lambda s: _SPAN_ORDER.get(s.get("name"), len(_SPAN_ORDER)))

    return spans, service or None
