"""Decorator-based automatic tracing for OpenTelemetry spans."""

from functools import wraps
from .traceability import get_trace_manager


def _get_service_name(self, request=None) -> str:
    """Extract service name from task_name, service_name attribute, or request payload."""
    service_name = getattr(self, 'service_name', None)
    if service_name:
        return service_name

    # For Orchestrator: extract task_type from request payload if available
    if request and isinstance(request, dict):
        task_type = request.get('task_type', '').lower()
        if task_type:
            return task_type

    task_name = getattr(self, 'task_name', self.__class__.__name__)
    service_name = task_name.replace('TaskService', '').lower()
    return service_name


def trace_stage(stage_name):
    """Decorator for automatic tracing of processing stages (sync)."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, request):
            import time
            import logging
            logger = logging.getLogger(__name__)
            trace_manager = get_trace_manager()
            service_name = _get_service_name(self, request)
            logger.info(f"[TRACE WRAPPER] {stage_name} START: service={service_name}, request_type={type(request).__name__}")
            start_time = time.time()
            span = trace_manager.trace_stage_start(service_name, stage_name, request)
            try:
                response = func(self, request)
                elapsed_ms = (time.time() - start_time) * 1000
                response_dict = response.dict() if response and hasattr(response, 'dict') else (response or {})
                if isinstance(response_dict, dict):
                    response_dict['elapsed_time_ms'] = elapsed_ms
                logger.info(f"[TRACE WRAPPER] {stage_name} END: response_type={type(response).__name__}, response_is_none={response is None}")
                logger.debug(f"[TRACE WRAPPER] {stage_name} response_dict keys: {list(response_dict.keys()) if isinstance(response_dict, dict) else 'N/A'}")
                trace_manager.trace_stage_end(span, response_dict)
                return response
            except Exception as e:
                logger.error(f"[TRACE WRAPPER] {stage_name} ERROR: {e}")
                span.span.end()
                raise
        return wrapper
    return decorator


def async_trace_stage(stage_name):
    """Decorator for automatic tracing of async processing stages. Supports variable signatures."""
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            import time
            import logging
            logger = logging.getLogger(__name__)
            trace_manager = get_trace_manager()
            # Extract request/payload from first positional argument or keyword arguments
            request = args[0] if args else kwargs.get('payload') or kwargs.get('request') or {}
            request_dict = request.dict() if hasattr(request, 'dict') else request
            service_name = _get_service_name(self, request_dict)
            logger.info(f"[ASYNC TRACE] {stage_name} START: service={service_name}, request_type={type(request_dict).__name__}")

            start_time = time.time()
            span = trace_manager.trace_stage_start(service_name, stage_name, request_dict)
            try:
                response = await func(self, *args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000
                response_dict = response.dict() if response and hasattr(response, 'dict') else (response or {})
                if isinstance(response_dict, dict):
                    response_dict['elapsed_time_ms'] = elapsed_ms
                logger.info(f"[ASYNC TRACE] {stage_name} END: response_type={type(response).__name__}, response_is_none={response is None}")
                logger.debug(f"[ASYNC TRACE] {stage_name} response_dict keys: {list(response_dict.keys()) if isinstance(response_dict, dict) else 'N/A'}")
                trace_manager.trace_stage_end(span, response_dict)
                return response
            except Exception as e:
                logger.error(f"[ASYNC TRACE] {stage_name} ERROR: {e}")
                span.span.end()
                raise
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


class TraceableService:
    """Mixin that auto-instruments standard pipeline stages with tracing."""

    @staticmethod
    def _wrap_with_trace(service_instance, method, stage_name):
        trace_manager = get_trace_manager()
        @wraps(method)
        def traced_method(request):
            span = trace_manager.trace_stage_start(service_instance.service_name, stage_name, request)
            try:
                response = method(request)
                trace_manager.trace_stage_end(span, response)
                return response
            except Exception:
                span.span.end()
                raise
        return traced_method

    def __init_subclass__(cls, **kwargs):
        """Auto-wrap standard stages: preprocess, resolve_model, triton_inference, postprocess, persist."""
        super().__init_subclass__(**kwargs)
        for stage in ["preprocess", "resolve_model", "triton_inference", "postprocess", "persist"]:
            if hasattr(cls, stage):
                setattr(cls, stage, trace_stage(stage)(getattr(cls, stage)))
