"""
Decorator-based tracing for automatic span lifecycle management.

This module provides two approaches for integrating OpenTelemetry tracing:

1. @trace_stage decorator: Mark individual methods for automatic tracing
   - Simple and explicit
   - Works with any method signature
   - Recommended for most use cases

2. TraceableService mixin: Auto-instrument all stage methods
   - Guarantees tracing even if subclasses override methods
   - Useful for enforcing instrumentation in class hierarchies
   - Works by wrapping methods at class initialization time

Usage:
    # Approach 1: Decorator
    @trace_stage("preprocess")
    def preprocess(self, request):
        return process(request)

    # Approach 2: Mixin (auto-wraps all stage methods)
    class OCRService(TraceableService):
        def preprocess(self, request):
            return process(request)
"""

from functools import wraps

from .traceability import get_trace_manager


def trace_stage(stage_name):
    """
    Decorator that wraps any method with automatic tracing.

    Automatically manages span lifecycle:
    - Creates span before method execution
    - Computes and attaches request attributes
    - Executes the wrapped method
    - Computes and attaches response attributes
    - Exports span on success or exception

    Args:
        stage_name: Name of the processing stage (e.g., "preprocess", "inference")

    Returns:
        Decorator function

    Usage:
        @trace_stage("preprocess")
        def preprocess(self, request):
            return self.preprocessor.run(request)

    Requirements:
        The decorated method's class must have:
        - self.service_name: Name of the service
        - self.trace_manager (optional): TraceManager instance (uses global if not set)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request):
            trace_manager = getattr(self, 'trace_manager', None) or get_trace_manager()

            span = trace_manager.trace_stage_start(
                self.service_name,
                stage_name,
                request
            )

            try:
                response = func(self, request)
                trace_manager.trace_stage_end(span, response)
                return response
            except Exception as e:
                # End span on error (no response attributes computed)
                span.span.end()
                raise

        return wrapper

    return decorator


class TraceableService:
    """
    Mixin class that auto-instruments all stage methods with tracing.

    Guarantees tracing is applied to standard pipeline stages,
    even if subclasses override the methods. This is useful for:
    - Enforcing observability across the class hierarchy
    - Preventing accidental loss of tracing
    - Reducing boilerplate (no need to manually decorate each method)

    Standard Stages:
        preprocess: Data preparation and validation
        resolve_model: Model selection/loading
        triton_inference: Model inference execution
        postprocess: Result formatting and validation
        persist: Saving results to storage

    Usage:
        class OCRService(TraceableService):
            service_name = "ocr"

            def preprocess(self, request):
                # Automatically traced with stage="preprocess"
                return cleaned_request

            def triton_inference(self, request):
                # Automatically traced with stage="triton_inference"
                return model_output

        service = OCRService()
        result = service.preprocess(request)  # Spans created and exported automatically
    """

    @staticmethod
    def _wrap_with_trace(service_instance, method, stage_name):
        """
        Helper to wrap a method with tracing logic.

        Args:
            service_instance: Instance of the service
            method: Method to wrap
            stage_name: Name of the processing stage

        Returns:
            Wrapped method with automatic span management
        """
        trace_manager = get_trace_manager()

        @wraps(method)
        def traced_method(request):
            span = trace_manager.trace_stage_start(
                service_instance.service_name,
                stage_name,
                request
            )
            try:
                response = method(request)
                trace_manager.trace_stage_end(span, response)
                return response
            except Exception:
                # End span on error
                span.span.end()
                raise

        return traced_method

    def __init_subclass__(cls, **kwargs):
        """
        Auto-wrap all stage methods when a subclass is created.

        Called automatically when a subclass is defined. Wraps all known
        stage methods with trace_stage decorators to ensure tracing happens
        even if methods are overridden in the subclass hierarchy.
        """
        super().__init_subclass__(**kwargs)

        # Standard pipeline stages
        stages = [
            "preprocess",
            "resolve_model",
            "triton_inference",
            "postprocess",
            "persist"
        ]

        for stage in stages:
            if hasattr(cls, stage):
                original_method = getattr(cls, stage)
                # Apply trace_stage decorator
                wrapped = trace_stage(stage)(original_method)
                setattr(cls, stage, wrapped)