"""Telemetry API endpoints for querying traces."""
import re
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.telemetry import SearchTracesResponse, TraceResponse
from app.utils.opensearch_client import OpenSearchTraceClient
from app.core.exceptions import InsufficientPermissionsError
from app.core.config import settings
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

# Role IDs (must match the seeded values in roles table)
_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2
_ROLE_TENANT_ADMIN = 5

# All allowed roles for telemetry access (roles that can access telemetry endpoints)
ALLOWED_ROLES = {_ROLE_ADMIN, _ROLE_MODERATOR, _ROLE_TENANT_ADMIN}

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
            "sources": [{"trace_id": {"terms": {"field": "context.trace_id.keyword"}}}],
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


def _build_traces_map(hits: list, tenant_filter: Optional[str]) -> dict:
    """Turn a list of raw span records into one summary record per trace (log).

    A single log is made up of several spans (request, model, ai-inference),
    each carrying different pieces of information: task_type lives on the
    'model' span, url lives on the 'request' span, and status can show up on
    more than one span. This walks the spans and, per trace_id, keeps the
    task_type from the 'model' span, the url from the 'request' span, and the
    first non-unknown status it sees (hits arrive newest-first, so that's the
    most recent span with a defined status - a trace's spans can disagree,
    e.g. a retried request, so this rule is what keeps each trace's status
    single-valued instead of double-counted later).

    This logic itself is unchanged from before this fix - it used to be
    written inline, once, only for the current page. It's now its own
    function so `_compute_full_breakdown` below can reuse the exact same
    rule instead of re-implementing it a second, possibly inconsistent, way.
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
            traces_map[trace_id] = {
                "trace_id": trace_id,
                "service": source.get("service_name") or "ai4x-inference",
                "task_type": None,
                "status": "unknown",
                "url": None,
                "tenant_id": tenant_filter or attrs.get("tenantId") or "system",
                "timestamp": source.get("@timestamp") or source.get("timestamp"),
            }
        elif not traces_map[trace_id]["service"] or traces_map[trace_id]["service"] == "ai4x-inference":
            # Upgrade the service name from a later span if a real name is present
            if source.get("service_name"):
                traces_map[trace_id]["service"] = source.get("service_name")

        # Extract task_type from model span
        if span_name == "model" and not traces_map[trace_id]["task_type"]:
            traces_map[trace_id]["task_type"] = attrs.get("task_type")

        # Extract url from request span
        if span_name == "request" and not traces_map[trace_id]["url"]:
            traces_map[trace_id]["url"] = attrs.get("url")

        # Extract status from any span
        if not traces_map[trace_id]["status"] or traces_map[trace_id]["status"] == "unknown":
            traces_map[trace_id]["status"] = attrs.get("status", "unknown")

    return traces_map


# Spans-per-trace ceiling used when sizing Step 3's per-page span fetch below.
# Keeps page_size * this under OpenSearch's default 10k result-window limit.
_SPAN_CEILING_PER_TRACE = 50

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

    Returns (by_level, by_task, truncated).
    """
    if not trace_ids:
        return {}, {}, False

    by_level = {}
    by_task = {}
    truncated = False
    semaphore = asyncio.Semaphore(_BREAKDOWN_CONCURRENCY)
    batches = [trace_ids[i:i + _BREAKDOWN_BATCH_SIZE] for i in range(0, len(trace_ids), _BREAKDOWN_BATCH_SIZE)]

    async def fetch_batch(batch: list) -> dict:
        trace_id_clauses = [{"match_phrase": {"context.trace_id": tid}} for tid in batch]
        async with semaphore:
            return await asyncio.to_thread(
                opensearch_client.search_traces,
                query={"bool": {"should": trace_id_clauses, "minimum_should_match": 1}},
                size=len(batch) * _BREAKDOWN_SPAN_CEILING_PER_TRACE,
                source_fields=["@timestamp", "name", "context.trace_id", "attributes", "service_name"],
            )

    responses = await asyncio.gather(*(fetch_batch(batch) for batch in batches))

    for batch, response in zip(batches, responses):
        hits = response.get("hits", {}).get("hits", [])
        batch_traces = _build_traces_map(hits, tenant_filter)

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
            task_key = trace.get("task_type") or "unknown"
            by_level[status_key] = by_level.get(status_key, 0) + 1
            by_task[task_key] = by_task.get(task_key, 0) + 1

    return by_level, by_task, truncated


def _check_permission_ids(request: Request, *allowed: int) -> None:
    """Raise if X-Permission-IDS header does not contain any of the allowed role IDs."""
    raw = request.headers.get("X-Permission-IDS", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}

    if not ids & set(allowed):
        raise InsufficientPermissionsError()


def _validate_telemetry_access(request: Request) -> None:
    """Validate that user has one of the allowed roles for telemetry access.

    Only roles 1 (admin), 2 (moderator), or 5 (tenant admin) are allowed.
    Raises InsufficientPermissionsError if user has role 3 (guest), 4 (user), or no role.
    """
    _check_permission_ids(request, *ALLOWED_ROLES)




def _is_admin(request: Request) -> bool:
    """Check if the user has admin/moderator role for trace access.
    Admin and Moderator can see all traces across all tenants.
    Returns True if user is admin or moderator, False otherwise.
    """
    try:
        _check_permission_ids(request, _ROLE_ADMIN, _ROLE_MODERATOR)
        return True
    except InsufficientPermissionsError:
        return False


def _get_tenant_id(request: Request) -> Optional[str]:
    """Caller's tenant from X-Tenant-Id (injected by the gateway from the validated JWT)."""
    return request.headers.get("X-Tenant-Id")


def _get_opensearch_client(request: Request) -> OpenSearchTraceClient:
    """Get OpenSearch client from app state."""
    client = getattr(request.app.state, "opensearch_client", None)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenSearch service unavailable",
        )
    return client


@router.get("/traces/search", response_model=SearchTracesResponse)
async def search_traces_opensearch(
    request: Request,
    task_types: Optional[str] = Query(None, description="Comma-separated task type filter (e.g. nmt,llm,asr)"),
    status_filter: Optional[str] = Query(None, description="Filter by status (success, failure, etc.)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (ADMIN only for other tenants)"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of traces per page"),
    opensearch_client: OpenSearchTraceClient = Depends(_get_opensearch_client),
):
    """
    Search traces from OpenSearch for the Logs Dashboard.

    Returns one page of matching logs (`data`) plus the true pagination
    `total`, and separately, summary counts (`aggregations`: total,
    by_level, by_task) covering EVERY log that matches the filters - not
    just the page being returned. The two are computed differently: `data`
    and `total` come from a single query (Step 2 below); the summary counts
    require looking at every matching log, so they're built via
    _collect_all_trace_ids + _compute_full_breakdown further down.
    """

    # Validate user has one of the allowed roles (1, 2, or 5)
    _validate_telemetry_access(request)

    try:
        is_admin = _is_admin(request)

        # Access is already gated at the gateway (traces.read). Here we only decide
        # breadth: admin sees all tenants (optionally narrowed by ?tenant_id); everyone
        # else is scoped to their own tenant and the client tenant_id is ignored.
        if is_admin:
            tenant_filter = tenant_id
            if tenant_filter:
                logger.info(f"ADMIN trace read - filtering by tenant_id={tenant_filter}")
        else:
            tenant_filter = _get_tenant_id(request)
            if not tenant_filter:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tenant_id in token for tenant-scoped trace access",
                )
            logger.info(f"Tenant-scoped trace read - tenant_id={tenant_filter}")

        # Build OpenSearch query to find matching traces, then return ALL spans for those traces
        filter_clauses = []

        if tenant_filter:
            filter_clauses.append({"match_phrase": {"attributes.tenantId": tenant_filter}})

        if task_types:
            types_list = [t.strip() for t in task_types.split(",") if t.strip()]
            if len(types_list) == 1:
                filter_clauses.append({"match_phrase": {"attributes.task_type": types_list[0]}})
            elif types_list:
                filter_clauses.append({
                    "bool": {
                        "should": [{"match_phrase": {"attributes.task_type": t}} for t in types_list],
                        "minimum_should_match": 1,
                    }
                })

        if status_filter:
            filter_clauses.append({"match_phrase": {"attributes.status": status_filter}})

        if start_date or end_date:
            range_query = {}
            if start_date:
                range_query["gte"] = start_date
            if end_date:
                range_query["lte"] = end_date
            filter_clauses.append({"range": {"@timestamp": range_query}})

        # Step 1: Find trace_ids that match the filters
        if filter_clauses:
            filter_query = {"bool": {"must": filter_clauses}}
        else:
            filter_query = {"match_all": {}}

        logger.info(f"Searching traces - task_types={task_types}, status={status_filter}, tenant={tenant_filter}")

        # Step 2: page the matching traces at the TRACE level, newest-first.
        # Collapsing on trace_id makes each result row one trace (not one span), so
        # from/size paginate over traces; sorting by @timestamp desc (the client
        # default) orders them by recency; the cardinality agg yields the distinct
        # trace count so page math reflects traces, not spans.
        offset = (page - 1) * page_size
        ids_response = opensearch_client.search_traces(
            query=filter_query,
            size=page_size,
            from_=offset,
            source_fields=["context.trace_id"],
            collapse={"field": "context.trace_id.keyword"},
            aggs={"trace_count": {"cardinality": {
                "field": "context.trace_id.keyword",
                "precision_threshold": _TOTAL_PRECISION_THRESHOLD,
            }}},
        )

        # Total count is the number of matching traces (not spans)
        total = ids_response.get("aggregations", {}).get("trace_count", {}).get("value", 0)

        _NULL_TRACE_ID = "0x" + "0" * 32

        # Preserve the newest-first order from the collapse result
        paginated_trace_ids = []
        for hit in ids_response.get("hits", {}).get("hits", []):
            trace_id = hit.get("_source", {}).get("context", {}).get("trace_id")
            if trace_id and trace_id != _NULL_TRACE_ID and trace_id not in paginated_trace_ids:
                paginated_trace_ids.append(trace_id)

        # Step 3: fetch ALL spans for the paged traces. Filters target single span
        # types (task_type on the 'model' span, url on 'request'), so we re-fetch the
        # full set per trace — unfiltered — to assemble complete metadata.
        traces_map = {}
        if paginated_trace_ids:
            trace_id_clauses = [{"match_phrase": {"context.trace_id": tid}} for tid in paginated_trace_ids]
            spans_response = opensearch_client.search_traces(
                query={"bool": {"should": trace_id_clauses, "minimum_should_match": 1}},
                size=len(paginated_trace_ids) * _SPAN_CEILING_PER_TRACE,
                source_fields=["@timestamp", "name", "context.trace_id", "attributes", "service_name"],
            )
            traces_map = _build_traces_map(spans_response.get("hits", {}).get("hits", []), tenant_filter)

        # Emit in the newest-first order established by the collapse page
        data = [traces_map[tid] for tid in paginated_trace_ids if tid in traces_map]

        # Calculate aggregations across ALL matching traces (not just this page) so the
        # summary cards match the pagination footer's total instead of the page size.
        is_capped = total > _MAX_BREAKDOWN_TRACE_IDS
        if is_capped:
            logger.warning(
                f"Trace breakdown capped at {_MAX_BREAKDOWN_TRACE_IDS} of {total} matching "
                "traces; by_level/by_task counts are partial for this filter."
            )
        all_trace_ids = _collect_all_trace_ids(opensearch_client, filter_query, min(total, _MAX_BREAKDOWN_TRACE_IDS))
        by_level, by_task, breakdown_truncated = await _compute_full_breakdown(opensearch_client, all_trace_ids, tenant_filter)
        is_partial = is_capped or breakdown_truncated

        return SearchTracesResponse(

            data=data,
            total=total,
            page=page,
            pageSize=page_size,
            aggregations={
                "total": total,
                "by_level": by_level,
                "by_task": by_task,
                "partial": is_partial,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching OpenSearch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching OpenSearch: {str(e)}",
        )



@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace_by_id(
    trace_id: str,
    request: Request,
    opensearch_client: OpenSearchTraceClient = Depends(_get_opensearch_client),
):
    """
    Get a specific trace by ID from OpenSearch.

    Args:
        trace_id: The trace ID to retrieve (hex format)

    Returns:
        Complete trace with all spans
    """
    try:
        _validate_telemetry_access(request)
        is_admin = _is_admin(request)
        tenant_scope = None if is_admin else _get_tenant_id(request)
        if not is_admin and not tenant_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant_id in token for tenant-scoped trace access",
            )

        logger.info(f"Getting trace {trace_id} from OpenSearch")

        # Query OpenSearch for all spans with matching trace_id
        response = opensearch_client.get_trace_by_id(trace_id, source_fields=[
            "@timestamp",
            "name",
            "context.trace_id",
            "context.parent_span_id",
            "status",
            "attributes",
            "service_name"
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

        # Transform spans from response
        spans = []
        service = None
        for hit in hits:
            source = hit.get("_source", {})
            if not service and source.get("service_name"):
                service = source.get("service_name")
            spans.append({
                "name": source.get("name"),
                "context": source.get("context", {}),
                "kind": source.get("kind"),
                "attributes": source.get("attributes", {}),
                "timestamp": source.get("@timestamp") or source.get("timestamp"),
            })

        # @timestamp is Fluent Bit's ingestion time, not the span's real OTel
        # end_time (no Time_Key override in fluent-bit.conf), so all spans in a
        # trace land within a few ms of each other regardless of actual duration
        # -- unusable for chronological ordering, and start_time/end_time never
        # reach this index. Every task type follows the same fixed span
        # sequence, so rank by name instead of by (unreliable) time.
        spans.sort(key=lambda s: _SPAN_ORDER.get(s.get("name"), len(_SPAN_ORDER)))

        trace_response = TraceResponse(
            trace_id=trace_id,
            service=service or "ai4x-inference",
            tenant_id=tenant_scope or "system",
            environment=settings.environment,
            hostname="unknown",
            spans=spans
        )

        logger.info(f"Successfully retrieved trace {trace_id} with {len(spans)} spans")
        return trace_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trace: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trace: {str(e)}",
        )
