"""
Orchestrator for routing inference requests to appropriate TaskServices.
Handles task routing, service resolution, and request/model span tracing.
"""

from typing import Any, Dict, List, Optional, Tuple
from fastapi import Request
import logging

from ai4i_core.observability import set_billed_state, set_metric_labels

from trace.request_span import (
    get_context_attributes,
    get_endpoint_path,
    traced_span,
)

from services.base.task_service import BaseTaskService
from services.service_fallback import (
    get_fallbacks,
    log_all_failed,
    log_failover,
    log_fallback_skipped,
)
from inference.inference_server_resolver import InferenceServerResolver
from utils.failover import AllServicesUnavailableError, failover_reason
from utils.http_status import http_status_for
from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY


logger = logging.getLogger(__name__)

# Allowed task types — kept here (not derived from the registry) because SMR
# routes without a registry entry of its own.
ALLOWED_TASK_TYPES = [
    "NMT", "ASR", "OCR", "NER", "TTS", "PII", "LANGUAGE_DETECTION",
    "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION",
    "AUDIO_LANGUAGE_DETECTION", "SMR",
]


class Orchestrator:
    """
    Orchestrator manages the routing and execution of inference requests.
    Coordinates between generic request envelopes and task-specific services.

    Errors propagate with their original types (`raise ... from`) — the route
    layer maps the exception cause chain to client-safe HTTP statuses, so no
    orchestrator-specific exception wrappers are needed.
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.logger = logger
        self.inference_server_resolver = InferenceServerResolver()
        self.task_service_registry: dict = TASK_SERVICE_REGISTRY

    async def route_inference(
        self,
        payload: Dict[str, Any],
        request: Optional[Request] = None,
    ) -> Dict[str, Any]:
        """
        Route inference request to appropriate TaskService.
        Extracts task_type and delegates to task-specific service for processing.

        Args:
            payload: Raw request payload dictionary
            request: Optional FastAPI Request object for reading path and method

        Returns:
            Serialized response dictionary

        Raises:
            ValueError: If task_type is not registered
            RuntimeError: If service resolution or inference fails
        """
        # Root span (parentID=null); traced_span owns timing + status. Its
        # status_code is the HTTP status the route returns (http_status_for,
        # shared with routes/inference.py): the billing consumer writes the
        # request's usage_events row from this span, and the Usage Dashboard
        # counts failures by it.
        with traced_span("request", root=True, classify_status=True, status_for=http_status_for) as attrs:
            attrs["url"] = str(request.url.path) if request else get_endpoint_path()
            attrs["method"] = request.method if request else ""
            attrs.update(get_context_attributes())
            # Which service and task the request was for, set before anything
            # can fail so a failed request still carries them: the service as
            # the client sent it, replaced by the resolved one below.
            attrs["task_type"] = str(payload.get("task_type", "")).lower()
            attrs["service_id"] = (
                (payload.get("config") or {}).get("serviceId") or payload.get("serviceId") or ""
            )

            task_type = payload.get("task_type", "").upper()
            self._validate_task_type(task_type)

            # Resolve service and model BEFORE creating task service
            service_info = await self._resolve_service_and_model(payload)
            attrs["service_id"] = service_info.get("serviceId") or attrs["service_id"]

            # Set as soon as it's known (covers the SMR-fallback-resolved case
            # too, via service_info["serviceId"]) so ObservabilityMiddleware
            # has it without re-parsing the body — same request.state.service_id
            # pattern the LLM chat route already uses in routes/inference.py.
            #
            # model_id is set here too (not bundled into the set_metric_labels
            # call below) for the same reason: it's already fully known from
            # service_info, unlike source_lang/target_lang which only exist
            # once task_service.process() has actually run. Setting it early
            # means a request that fails/raises during process() (e.g. a 502
            # from the upstream Triton server) still gets model_id on its
            # metrics — set_metric_labels() never resets a field the caller
            # doesn't pass (see its docstring), so this survives the second,
            # post-process() call below untouched.
            if request is not None:
                request.state.service_id = service_info.get("serviceId", "") or ""
                set_metric_labels(request, model_id=service_info.get("model_id") or "")

            # Tier entitlement check (API key calls only; JWT has empty X-Tier-ID)
            self._enforce_tier_gate(service_info, request)

            # Run the requested service; if it's unreachable, the Application's
            # fallbacks for it in order (none configured → exactly as before).
            requested_id = service_info.get("serviceId") or ""
            task_service, task_response, served_info, _ = await self._run_with_fallbacks(
                payload, service_info, None, request
            )

            served_id = served_info.get("serviceId") or ""
            fallback_used = served_id != requested_id
            attrs["service_id"] = served_id
            attrs["fallback_used"] = fallback_used
            if request is not None and fallback_used:
                request.state.service_id = served_id
                set_metric_labels(request, model_id=served_info.get("model_id") or "")
            if isinstance(task_response, dict):
                model_block = task_response.get("model")
                if isinstance(model_block, dict):
                    model_block["serviceId"] = served_id

            # Mirror the count task_service already computed once onto
            # request.state, so ObservabilityMiddleware can read it instead of
            # re-deriving its own from the raw body. Input only: non-LLM
            # billing/metrics are input-only (billing reads the span, and the
            # non-LLM Prometheus metrics track input units only). Language
            # labels are metric labels (not billing) — set separately.
            if request is not None:
                set_billed_state(
                    request,
                    billed_input=getattr(task_service, "billed_input", 0),
                )
                set_metric_labels(
                    request,
                    source_lang=getattr(task_service, "source_lang", ""),
                    target_lang=getattr(task_service, "target_lang", ""),
                )

            return task_response.dict() if hasattr(task_response, 'dict') else task_response

    @staticmethod
    def _enforce_tier_gate(service_info: Dict[str, Any], request: Optional[Request]) -> None:
        """PermissionError (403) when the caller's Tier may not use this
        service. Only API-key calls carry X-Tier-ID; services with no Tier
        assignment are open to every Tier."""
        if request is None:
            return
        tier_id = request.headers.get("X-Tier-ID", "")
        if not tier_id:
            return
        allowed_tiers = [str(t) for t in service_info.get("tier_ids", [])]
        if allowed_tiers and tier_id not in allowed_tiers:
            raise PermissionError(
                f"Service '{service_info.get('serviceId', '')}' is not available for your quota"
            )

    @staticmethod
    def _partly_billed(task_service: BaseTaskService) -> bool:
        """True once a group of this attempt was served — and billed (see
        BaseTaskService.billed_groups). Failover is safe only before that."""
        return getattr(task_service, "billed_groups", 0) > 0

    @staticmethod
    def _with_service_id(payload: Dict[str, Any], service_id: str) -> Dict[str, Any]:
        """The payload aimed at another service — config.serviceId is what
        resolution reads first, and the response echoes it back."""
        return {**payload, "config": {**(payload.get("config") or {}), "serviceId": service_id}}

    async def _run_with_fallbacks(
        self,
        payload: Dict[str, Any],
        service_info: Dict[str, Any],
        fallbacks: Optional[List[str]],
        request: Optional[Request],
    ) -> Tuple[BaseTaskService, Any, Dict[str, Any], List[Tuple[str, str]]]:
        """Run the requested service, then each fallback in order, until one
        succeeds.

        Moves on only when the model is unreachable (timeout, connection
        error, 5xx — see utils/failover.py). Any other failure of the
        requested service (bad input, 4xx, …) is raised unchanged, and so is
        every failure when no fallback is configured. A fallback that can't
        be used (unpublished, out of Tier, rejects the input) is skipped.
        A failed attempt's ai-inference span carries zero tokens, so only
        the service that answers is billed; each failover is logged
        (service_failover).

        ``fallbacks`` None = look them up only once the requested service has
        actually failed over, so a healthy request never pays for the lookup.

        Returns (task_service, response, served service_info, failed attempts).
        """
        requested_id = service_info.get("serviceId") or ""
        attempts: List[Tuple[str, str]] = []

        task_service = self._get_task_service(service_info)
        try:
            response = await task_service.process(payload, service_info)
            return task_service, response, service_info, attempts
        except Exception as exc:
            reason = failover_reason(exc)
            if reason is None:
                raise
            if self._partly_billed(task_service):
                # A fallback re-runs the whole payload, which would bill the
                # groups that already succeeded a second time — return the
                # error as it is today instead.
                logger.warning(
                    "service_failover_not_attempted requested_service_id=%s reason=%s "
                    "billed_groups=%d (already partly served)",
                    requested_id, reason, task_service.billed_groups,
                )
                raise
            if fallbacks is None:
                fallbacks = await get_fallbacks(requested_id)
            if not fallbacks:
                raise
            attempts.append((requested_id, reason))

        for index, service_id in enumerate(fallbacks, start=1):
            failed_id, failed_reason = attempts[-1]
            log_failover(
                requested=requested_id, failed=failed_id, next_service=service_id,
                reason=failed_reason, attempt=index,
            )
            attempt_payload = self._with_service_id(payload, service_id)
            try:
                info = await self._resolve_service_and_model(attempt_payload)
                # auth-service checks Tier only when the fallbacks are saved;
                # the tenant's Tier or the service's tier_ids may have changed
                # since, so re-check against the live catalogue.
                self._enforce_tier_gate(info, request)
                task_service = self._get_task_service(info)
            except Exception as exc:
                log_fallback_skipped(requested=requested_id, skipped=service_id, reason=type(exc).__name__)
                attempts.append((service_id, "not_eligible"))
                continue
            try:
                response = await task_service.process(attempt_payload, info)
                return task_service, response, info, attempts
            except Exception as exc:
                attempts.append((service_id, failover_reason(exc) or "fallback_rejected"))
                if self._partly_billed(task_service):
                    # Same rule as for the requested service: this fallback
                    # already billed part of the payload, so the next one
                    # must not bill it again.
                    break

        log_all_failed(requested=requested_id, attempts=attempts)
        raise AllServicesUnavailableError(requested_id, attempts)

    def _validate_task_type(self, task_type: str) -> None:
        """Raise ValueError if task_type is not a known task."""
        if task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(
                f"Unknown task_type: {task_type}. Allowed: {', '.join(ALLOWED_TASK_TYPES)}"
            )

    def _get_task_service(self, service_info: Dict[str, Any]) -> BaseTaskService:
        """
        Instantiate the task service for the resolved service_info.
        Looks up TASK_SERVICE_REGISTRY by mm_models.class_instance.

        Raises:
            RuntimeError: If class_instance is unset or unknown (platform/config
                          gap, not a client error)
        """
        # class_instance comes from mm_models.class_instance via the resolver —
        # adding a model in the platform needs no code change here.
        class_instance = service_info.get("class_instance")
        if not class_instance:
            raise RuntimeError(
                f"No class_instance set on model for serviceId='"
                f"{service_info.get('name', '')}'. "
                f"Set the classInstance field on the model in the platform."
            )

        service_class = self.task_service_registry.get(class_instance)
        if not service_class:
            raise RuntimeError(
                f"Unknown class_instance '{class_instance}'. "
                f"Register it in task_service_registry.py."
            )

        self.logger.debug(
            f"Instantiating {class_instance} for serviceId='{service_info.get('name', '')}'"
        )
        return service_class(service_info=service_info)  # type: ignore

    async def _resolve_service_and_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve the model service details from the raw request payload.
        Extracted here so the Orchestrator can route to the correct model-specific
        TaskService class before instantiation, rather than always mapping task_type
        to a single fixed service.

        Args:
            payload: Raw request payload dictionary (must contain config.serviceId
                     or a top-level serviceId field)

        Returns:
            Dict with keys: serviceId, name, endpoint, api_key, adapter_config, ...

        Raises:
            RuntimeError: If the service cannot be resolved
        """
        with traced_span("model") as attrs:
            attrs["task_type"] = payload.get("task_type", "").upper()
            attrs.update(get_context_attributes())

            # Extract serviceId: check config block first, then top-level
            config_block = payload.get("config") or {}
            serviceId = (
                config_block.get("serviceId") if isinstance(config_block, dict) else None
            ) or payload.get("serviceId")

            if not serviceId:
                # Fall back to SMR or a safe default
                serviceId = await self.inference_server_resolver.resolve_smr_service(payload)
                self.logger.warning(
                    f"No serviceId in payload, SMR resolved to: {serviceId}"
                )

            attrs["service_id"] = serviceId
            self.logger.debug(f"Resolving service: {serviceId}")
            try:
                service_info = await self.inference_server_resolver.resolve_service(serviceId)
            except Exception as e:
                # No str(e) AND no exc_info=True — both leak the URL.
                # str(e) of httpx-class errors embeds the request URL;
                # exc_info=True bakes the full traceback (including the
                # chained exception's __str__) into the formatted log
                # record, which ships to OpenSearch via fluent-bit and
                # surfaces in the Logs Dashboard.
                # The `from e` chain still preserves the exception for
                # ad-hoc server-side inspection (debug session, post-mortem
                # via container shell) without writing it to stdout.
                self.logger.error(
                    "Failed to resolve service '%s': %s",
                    serviceId, type(e).__name__,
                )
                raise RuntimeError(
                    f"Orchestrator: Failed to resolve service '{serviceId}'"
                ) from e

            if not service_info.get("is_published", False):
                raise LookupError(
                    f"Service '{serviceId}' is not published and cannot be used for inference"
                )

            adapter_cfg = service_info.get("adapter_config") or {}
            attrs["model_name"] = service_info.get("name", "")
            attrs["model_version"] = (
                service_info.get("model_version") or adapter_cfg.get("model_version", "unknown")
            )
            # resolve_service()'s returned dict never carries the id it was
            # resolved from — stash it here so run_inference can copy it onto
            # the ai-inference span (the PPU Kafka consumer bills on service_id
            # read from that span only, mirroring the LLM proxy's approach).
            service_info["serviceId"] = serviceId
            return service_info
