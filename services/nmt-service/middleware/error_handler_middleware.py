"""
Global error handler middleware for consistent error responses.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id, get_logger

from middleware.exceptions import (
    AuthenticationError, 
    AuthorizationError, 
    RateLimitExceededError,
    ErrorDetail
)
import logging
import time
import traceback

logger = get_logger(__name__)
tracer = trace.get_tracer("nmt-service")


def add_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for common exceptions."""
    
    
    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError):
        """Handle authentication errors."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        correlation_id = get_correlation_id(request)
        
        if tracer:
            # Create detailed trace structure similar to successful requests
            # This ensures failed requests also show detailed spans in Jaeger
            with tracer.start_as_current_span("nmt.inference") as main_span:
                main_span.set_attribute("http.method", method)
                main_span.set_attribute("http.route", path)
                main_span.set_attribute("http.status_code", 401)
                if correlation_id:
                    main_span.set_attribute("correlation.id", correlation_id)
                
                # Try to extract request details if available
                service_id = "unknown"
                source_lang = "unknown"
                target_lang = "unknown"
                input_count = 0
                
                try:
                    # Try to get request body if it was parsed
                    if hasattr(request.state, "parsed_body"):
                        body = request.state.parsed_body
                        if isinstance(body, dict):
                            if "config" in body and isinstance(body["config"], dict):
                                service_id = body["config"].get("serviceId", "unknown")
                                main_span.set_attribute("nmt.service_id", service_id)
                                if "language" in body["config"]:
                                    lang = body["config"]["language"]
                                    if isinstance(lang, dict):
                                        source_lang = lang.get("sourceLanguage", "unknown")
                                        target_lang = lang.get("targetLanguage", "unknown")
                                        main_span.set_attribute("nmt.source_language", source_lang)
                                        main_span.set_attribute("nmt.target_language", target_lang)
                            if "input" in body:
                                input_count = len(body["input"]) if isinstance(body["input"], list) else 0
                                main_span.set_attribute("nmt.input_count", input_count)
                except Exception:
                    pass  # Ignore if we can't extract body
                
                # 1. Identity & Context Attached - Create detailed child span (matching successful flow)
                with tracer.start_as_current_span("nmt.identity.context_attached") as identity_span:
                    identity_span.set_attribute("tenant.name", "unknown")
                    identity_span.set_attribute("tenant.budget", "N/A")
                    identity_span.set_attribute("tenant.daily_quota", "N/A")
                    identity_span.set_attribute("tenant.data_tier", "N/A")
                    identity_span.set_attribute("contract.channel", "N/A")
                    identity_span.set_attribute("contract.use_case", "N/A")
                    identity_span.set_attribute("contract.sensitivity", "N/A")
                    identity_span.set_attribute("contract.sla", "N/A")
                    identity_span.set_attribute("runtime.language", f"{source_lang} → {target_lang}")
                    identity_span.set_attribute("auth.failed", True)
                    identity_span.set_attribute("error.type", "AuthenticationError")
                    identity_span.set_attribute("error.message", "Authentication failed before context attachment")
                    identity_span.set_status(Status(StatusCode.ERROR, "Authentication failed before context attachment"))
                
                # 2. Policy Check - Create detailed child span (matching successful flow)
                with tracer.start_as_current_span("nmt.policy.check") as policy_span:
                    policy_span.set_attribute("policy.budget_remaining", "N/A")
                    policy_span.set_attribute("policy.daily_quota_used", "N/A")
                    policy_span.set_attribute("policy.data_residency", "N/A")
                    policy_span.set_attribute("policy.language", f"{source_lang} → {target_lang}")
                    policy_span.set_attribute("policy.status", "REJECTED")
                    policy_span.set_attribute("policy.rejection_reason", "authentication_failed")
                    policy_span.set_attribute("error.type", "AuthenticationError")
                    policy_span.set_attribute("error.message", "Authentication failed - policy check rejected")
                    policy_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                
                # 3. Smart Routing Decision - Create detailed child span (matching successful flow)
                with tracer.start_as_current_span("nmt.smart_routing.decision") as routing_span:
                    routing_span.set_attribute("routing.primary_provider", "N/A")
                    routing_span.set_attribute("routing.fallback_provider", "N/A")
                    routing_span.set_attribute("routing.auto_switch", "Disabled")
                    routing_span.set_attribute("routing.quality_target", "N/A")
                    routing_span.set_attribute("routing.latency_target", "N/A")
                    routing_span.set_attribute("routing.estimated_cost", "N/A")
                    routing_span.set_attribute("routing.status", "BLOCKED")
                    routing_span.set_attribute("routing.block_reason", "authentication_failed")
                    routing_span.set_attribute("error.type", "AuthenticationError")
                    routing_span.set_attribute("error.message", "Authentication failed - routing blocked")
                    routing_span.set_status(Status(StatusCode.ERROR, "Authentication failed - routing blocked"))
                
                # 4. Process Batch - Create span showing it was blocked (matching successful flow structure)
                with tracer.start_as_current_span("nmt.process_batch") as process_span:
                    process_span.set_attribute("batch.size", input_count)
                    process_span.set_attribute("batch.status", "BLOCKED")
                    process_span.set_attribute("block_reason", "authentication_failed")
                    
                    # Nested spans for process_batch (matching successful flow)
                    with tracer.start_as_current_span("nmt.get_model_name") as model_span:
                        model_span.set_attribute("model.name", "N/A")
                        model_span.set_attribute("service_id", service_id)
                        model_span.set_attribute("error.type", "AuthenticationError")
                        model_span.set_attribute("error.message", "Authentication failed - model name not retrieved")
                        model_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                    
                    with tracer.start_as_current_span("nmt.preprocess_texts") as preprocess_span:
                        preprocess_span.set_attribute("text_count", input_count)
                        preprocess_span.set_attribute("status", "SKIPPED")
                        preprocess_span.set_attribute("skip_reason", "authentication_failed")
                        preprocess_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                    
                    with tracer.start_as_current_span("nmt.create_request_record") as record_span:
                        record_span.set_attribute("status", "SKIPPED")
                        record_span.set_attribute("skip_reason", "authentication_failed")
                        record_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                    
                    process_span.set_attribute("error.type", "AuthenticationError")
                    process_span.set_attribute("error.message", "Authentication failed - batch processing blocked")
                    process_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                
                # 5. Format Response - Create span (matching successful flow)
                with tracer.start_as_current_span("nmt.format_response") as format_span:
                    format_span.set_attribute("output_count", 0)
                    format_span.set_attribute("status", "SKIPPED")
                    format_span.set_attribute("skip_reason", "authentication_failed")
                    format_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                
                # 6. Save Results - Create span (matching successful flow)
                with tracer.start_as_current_span("nmt.save_results") as save_span:
                    save_span.set_attribute("results_count", 0)
                    save_span.set_attribute("status", "SKIPPED")
                    save_span.set_attribute("skip_reason", "authentication_failed")
                    save_span.set_status(Status(StatusCode.ERROR, "Authentication failed"))
                
                # 7. Update Request Status - Create span (matching successful flow)
                with tracer.start_as_current_span("nmt.update_request_status") as status_span:
                    status_span.set_attribute("request_status", "FAILED")
                    status_span.set_attribute("failure_reason", "authentication_failed")
                    status_span.set_attribute("error.type", "AuthenticationError")
                    status_span.set_attribute("error.message", exc.message)
                    status_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # 8. Request Reject - Final rejection point
                with tracer.start_as_current_span("request.reject") as reject_span:
                    reject_span.set_attribute("auth.operation", "reject_authentication")
                    reject_span.set_attribute("auth.rejected", True)
                    reject_span.set_attribute("error.type", "AuthenticationError")
                    reject_span.set_attribute("error.reason", "authentication_failed")
                    reject_span.set_attribute("error.message", exc.message)
                    reject_span.set_attribute("error.code", "AUTHENTICATION_ERROR")
                    reject_span.set_attribute("http.status_code", 401)
                    reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # Mark main span as error
                main_span.set_attribute("error", True)
                main_span.set_attribute("error.type", "AuthenticationError")
                main_span.set_attribute("error.message", exc.message)
                main_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        # Explicit logging to ensure 401 errors appear in OpenSearch
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        processing_time = 0.001  # Minimal time for auth errors
        
        log_context = {
            "method": method,
            "path": path,
            "status_code": 401,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_type": "AuthenticationError",
            "error_code": "AUTHENTICATION_ERROR",
            "error_message": exc.message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        try:
            logger.warning(
                f"{method} {path} - 401 - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        except Exception as log_exc:
            logging.warning(
                f"401 Authentication Error: {method} {path} - {exc.message}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHENTICATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=401,
            content={"detail": error_detail.dict()}
        )
    
    
    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError):
        """Handle authorization errors."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        correlation_id = get_correlation_id(request)
        
        if tracer:
            # Create detailed trace structure similar to successful requests
            with tracer.start_as_current_span("nmt.inference") as main_span:
                main_span.set_attribute("http.method", method)
                main_span.set_attribute("http.route", path)
                main_span.set_attribute("http.status_code", 403)
                if correlation_id:
                    main_span.set_attribute("correlation.id", correlation_id)
                
                # Try to extract request details if available
                service_id = "unknown"
                source_lang = "unknown"
                target_lang = "unknown"
                input_count = 0
                user_id = getattr(request.state, "user_id", None)
                
                try:
                    if hasattr(request.state, "parsed_body"):
                        body = request.state.parsed_body
                        if isinstance(body, dict):
                            if "config" in body and isinstance(body["config"], dict):
                                service_id = body["config"].get("serviceId", "unknown")
                                main_span.set_attribute("nmt.service_id", service_id)
                                if "language" in body["config"]:
                                    lang = body["config"]["language"]
                                    if isinstance(lang, dict):
                                        source_lang = lang.get("sourceLanguage", "unknown")
                                        target_lang = lang.get("targetLanguage", "unknown")
                                        main_span.set_attribute("nmt.source_language", source_lang)
                                        main_span.set_attribute("nmt.target_language", target_lang)
                            if "input" in body:
                                input_count = len(body["input"]) if isinstance(body["input"], list) else 0
                                main_span.set_attribute("nmt.input_count", input_count)
                except Exception:
                    pass
                
                # 1. Identity & Context Attached - Create detailed child span
                with tracer.start_as_current_span("nmt.identity.context_attached") as identity_span:
                    if user_id:
                        identity_span.set_attribute("user.id", str(user_id))
                    identity_span.set_attribute("tenant.name", "unknown")
                    identity_span.set_attribute("tenant.budget", "N/A")
                    identity_span.set_attribute("tenant.daily_quota", "N/A")
                    identity_span.set_attribute("tenant.data_tier", "N/A")
                    identity_span.set_attribute("contract.channel", "N/A")
                    identity_span.set_attribute("contract.use_case", "N/A")
                    identity_span.set_attribute("contract.sensitivity", "N/A")
                    identity_span.set_attribute("contract.sla", "N/A")
                    identity_span.set_attribute("runtime.language", f"{source_lang} → {target_lang}")
                    identity_span.set_attribute("auth.authorized", False)
                    identity_span.set_attribute("error.type", "AuthorizationError")
                    identity_span.set_attribute("error.message", "Authorization failed")
                    identity_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                
                # 2. Policy Check - Create detailed child span
                with tracer.start_as_current_span("nmt.policy.check") as policy_span:
                    policy_span.set_attribute("policy.budget_remaining", "N/A")
                    policy_span.set_attribute("policy.daily_quota_used", "N/A")
                    policy_span.set_attribute("policy.data_residency", "N/A")
                    policy_span.set_attribute("policy.language", f"{source_lang} → {target_lang}")
                    policy_span.set_attribute("policy.status", "REJECTED")
                    policy_span.set_attribute("policy.rejection_reason", "authorization_failed")
                    policy_span.set_attribute("error.type", "AuthorizationError")
                    policy_span.set_attribute("error.message", "Authorization failed - policy check rejected")
                    policy_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                
                # 3. Smart Routing Decision - Create detailed child span
                with tracer.start_as_current_span("nmt.smart_routing.decision") as routing_span:
                    routing_span.set_attribute("routing.primary_provider", "N/A")
                    routing_span.set_attribute("routing.fallback_provider", "N/A")
                    routing_span.set_attribute("routing.auto_switch", "Disabled")
                    routing_span.set_attribute("routing.quality_target", "N/A")
                    routing_span.set_attribute("routing.latency_target", "N/A")
                    routing_span.set_attribute("routing.estimated_cost", "N/A")
                    routing_span.set_attribute("routing.status", "BLOCKED")
                    routing_span.set_attribute("routing.block_reason", "authorization_failed")
                    routing_span.set_attribute("error.type", "AuthorizationError")
                    routing_span.set_attribute("error.message", "Authorization failed - routing blocked")
                    routing_span.set_status(Status(StatusCode.ERROR, "Authorization failed - routing blocked"))
                
                # 4. Process Batch - Create span showing it was blocked
                with tracer.start_as_current_span("nmt.process_batch") as process_span:
                    process_span.set_attribute("batch.size", input_count)
                    process_span.set_attribute("batch.status", "BLOCKED")
                    process_span.set_attribute("block_reason", "authorization_failed")
                    
                    # Nested spans for process_batch
                    with tracer.start_as_current_span("nmt.get_model_name") as model_span:
                        model_span.set_attribute("model.name", "N/A")
                        model_span.set_attribute("service_id", service_id)
                        model_span.set_attribute("error.type", "AuthorizationError")
                        model_span.set_attribute("error.message", "Authorization failed - model name not retrieved")
                        model_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                    
                    with tracer.start_as_current_span("nmt.preprocess_texts") as preprocess_span:
                        preprocess_span.set_attribute("text_count", input_count)
                        preprocess_span.set_attribute("status", "SKIPPED")
                        preprocess_span.set_attribute("skip_reason", "authorization_failed")
                        preprocess_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                    
                    with tracer.start_as_current_span("nmt.create_request_record") as record_span:
                        record_span.set_attribute("status", "SKIPPED")
                        record_span.set_attribute("skip_reason", "authorization_failed")
                        record_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                    
                    process_span.set_attribute("error.type", "AuthorizationError")
                    process_span.set_attribute("error.message", "Authorization failed - batch processing blocked")
                    process_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                
                # 5. Format Response - Create span
                with tracer.start_as_current_span("nmt.format_response") as format_span:
                    format_span.set_attribute("output_count", 0)
                    format_span.set_attribute("status", "SKIPPED")
                    format_span.set_attribute("skip_reason", "authorization_failed")
                    format_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                
                # 6. Save Results - Create span
                with tracer.start_as_current_span("nmt.save_results") as save_span:
                    save_span.set_attribute("results_count", 0)
                    save_span.set_attribute("status", "SKIPPED")
                    save_span.set_attribute("skip_reason", "authorization_failed")
                    save_span.set_status(Status(StatusCode.ERROR, "Authorization failed"))
                
                # 7. Update Request Status - Create span
                with tracer.start_as_current_span("nmt.update_request_status") as status_span:
                    status_span.set_attribute("request_status", "FAILED")
                    status_span.set_attribute("failure_reason", "authorization_failed")
                    status_span.set_attribute("error.type", "AuthorizationError")
                    status_span.set_attribute("error.message", exc.message)
                    status_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # 8. Request Reject - Final rejection point
                with tracer.start_as_current_span("request.reject") as reject_span:
                    reject_span.set_attribute("auth.operation", "reject_authorization")
                    reject_span.set_attribute("auth.rejected", True)
                    reject_span.set_attribute("error.type", "AuthorizationError")
                    reject_span.set_attribute("error.reason", "authorization_failed")
                    reject_span.set_attribute("error.message", exc.message)
                    reject_span.set_attribute("error.code", "AUTHORIZATION_ERROR")
                    reject_span.set_attribute("http.status_code", 403)
                    reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # Mark main span as error
                main_span.set_attribute("error", True)
                main_span.set_attribute("error.type", "AuthorizationError")
                main_span.set_attribute("error.message", exc.message)
                main_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        # Explicit logging to ensure 403 errors appear in OpenSearch
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        processing_time = 0.001  # Minimal time for auth errors
        
        log_context = {
            "method": method,
            "path": path,
            "status_code": 403,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_type": "AuthorizationError",
            "error_code": "AUTHORIZATION_ERROR",
            "error_message": exc.message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        try:
            logger.warning(
                f"{method} {path} - 403 - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        except Exception as log_exc:
            logging.warning(
                f"403 Authorization Error: {method} {path} - {exc.message}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="AUTHORIZATION_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=403,
            content={"detail": error_detail.dict()}
        )
    
    
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_error_handler(request: Request, exc: RateLimitExceededError):
        """Handle rate limit exceeded errors."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        correlation_id = get_correlation_id(request)
        
        if tracer:
            # Create detailed trace structure for rate limit errors
            with tracer.start_as_current_span("nmt.inference") as main_span:
                main_span.set_attribute("http.method", method)
                main_span.set_attribute("http.route", path)
                main_span.set_attribute("http.status_code", 429)
                if correlation_id:
                    main_span.set_attribute("correlation.id", correlation_id)
                
                # Try to extract request details if available
                service_id = "unknown"
                source_lang = "unknown"
                target_lang = "unknown"
                input_count = 0
                user_id = getattr(request.state, "user_id", None)
                api_key_id = getattr(request.state, "api_key_id", None)
                
                try:
                    if hasattr(request.state, "parsed_body"):
                        body = request.state.parsed_body
                        if isinstance(body, dict):
                            if "config" in body and isinstance(body["config"], dict):
                                service_id = body["config"].get("serviceId", "unknown")
                                main_span.set_attribute("nmt.service_id", service_id)
                                if "language" in body["config"]:
                                    lang = body["config"]["language"]
                                    if isinstance(lang, dict):
                                        source_lang = lang.get("sourceLanguage", "unknown")
                                        target_lang = lang.get("targetLanguage", "unknown")
                                        main_span.set_attribute("nmt.source_language", source_lang)
                                        main_span.set_attribute("nmt.target_language", target_lang)
                            if "input" in body:
                                input_count = len(body["input"]) if isinstance(body["input"], list) else 0
                                main_span.set_attribute("nmt.input_count", input_count)
                except Exception:
                    pass
                
                # 1. Identity & Context Attached - Create detailed child span
                with tracer.start_as_current_span("nmt.identity.context_attached") as identity_span:
                    if user_id:
                        identity_span.set_attribute("user.id", str(user_id))
                    if api_key_id:
                        identity_span.set_attribute("api_key.id", str(api_key_id))
                    identity_span.set_attribute("tenant.name", "unknown")
                    identity_span.set_attribute("tenant.budget", "N/A")
                    identity_span.set_attribute("tenant.daily_quota", "N/A")
                    identity_span.set_attribute("tenant.data_tier", "N/A")
                    identity_span.set_attribute("contract.channel", "N/A")
                    identity_span.set_attribute("contract.use_case", "N/A")
                    identity_span.set_attribute("contract.sensitivity", "N/A")
                    identity_span.set_attribute("contract.sla", "N/A")
                    identity_span.set_attribute("runtime.language", f"{source_lang} → {target_lang}")
                    identity_span.set_attribute("rate_limit.exceeded", True)
                    identity_span.set_attribute("error.type", "RateLimitExceededError")
                    identity_span.set_attribute("error.message", "Rate limit exceeded before context attachment")
                    identity_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                
                # 2. Policy Check - Create detailed child span
                with tracer.start_as_current_span("nmt.policy.check") as policy_span:
                    policy_span.set_attribute("policy.budget_remaining", "N/A")
                    policy_span.set_attribute("policy.daily_quota_used", "N/A")
                    policy_span.set_attribute("policy.data_residency", "N/A")
                    policy_span.set_attribute("policy.language", f"{source_lang} → {target_lang}")
                    policy_span.set_attribute("policy.status", "REJECTED")
                    policy_span.set_attribute("policy.rejection_reason", "rate_limit_exceeded")
                    policy_span.set_attribute("rate_limit.retry_after", exc.retry_after)
                    policy_span.set_attribute("error.type", "RateLimitExceededError")
                    policy_span.set_attribute("error.message", "Rate limit exceeded - policy check rejected")
                    policy_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                
                # 3. Smart Routing Decision - Create detailed child span
                with tracer.start_as_current_span("nmt.smart_routing.decision") as routing_span:
                    routing_span.set_attribute("routing.primary_provider", "N/A")
                    routing_span.set_attribute("routing.fallback_provider", "N/A")
                    routing_span.set_attribute("routing.auto_switch", "Disabled")
                    routing_span.set_attribute("routing.quality_target", "N/A")
                    routing_span.set_attribute("routing.latency_target", "N/A")
                    routing_span.set_attribute("routing.estimated_cost", "N/A")
                    routing_span.set_attribute("routing.status", "BLOCKED")
                    routing_span.set_attribute("routing.block_reason", "rate_limit_exceeded")
                    routing_span.set_attribute("error.type", "RateLimitExceededError")
                    routing_span.set_attribute("error.message", "Rate limit exceeded - routing blocked")
                    routing_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded - routing blocked"))
                
                # 4. Process Batch - Create span showing it was blocked
                with tracer.start_as_current_span("nmt.process_batch") as process_span:
                    process_span.set_attribute("batch.size", input_count)
                    process_span.set_attribute("batch.status", "BLOCKED")
                    process_span.set_attribute("block_reason", "rate_limit_exceeded")
                    
                    # Nested spans for process_batch
                    with tracer.start_as_current_span("nmt.get_model_name") as model_span:
                        model_span.set_attribute("model.name", "N/A")
                        model_span.set_attribute("service_id", service_id)
                        model_span.set_attribute("error.type", "RateLimitExceededError")
                        model_span.set_attribute("error.message", "Rate limit exceeded - model name not retrieved")
                        model_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                    
                    with tracer.start_as_current_span("nmt.preprocess_texts") as preprocess_span:
                        preprocess_span.set_attribute("text_count", input_count)
                        preprocess_span.set_attribute("status", "SKIPPED")
                        preprocess_span.set_attribute("skip_reason", "rate_limit_exceeded")
                        preprocess_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                    
                    with tracer.start_as_current_span("nmt.create_request_record") as record_span:
                        record_span.set_attribute("status", "SKIPPED")
                        record_span.set_attribute("skip_reason", "rate_limit_exceeded")
                        record_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                    
                    process_span.set_attribute("error.type", "RateLimitExceededError")
                    process_span.set_attribute("error.message", "Rate limit exceeded - batch processing blocked")
                    process_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                
                # 5. Format Response - Create span
                with tracer.start_as_current_span("nmt.format_response") as format_span:
                    format_span.set_attribute("output_count", 0)
                    format_span.set_attribute("status", "SKIPPED")
                    format_span.set_attribute("skip_reason", "rate_limit_exceeded")
                    format_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                
                # 6. Save Results - Create span
                with tracer.start_as_current_span("nmt.save_results") as save_span:
                    save_span.set_attribute("results_count", 0)
                    save_span.set_attribute("status", "SKIPPED")
                    save_span.set_attribute("skip_reason", "rate_limit_exceeded")
                    save_span.set_status(Status(StatusCode.ERROR, "Rate limit exceeded"))
                
                # 7. Update Request Status - Create span
                with tracer.start_as_current_span("nmt.update_request_status") as status_span:
                    status_span.set_attribute("request_status", "FAILED")
                    status_span.set_attribute("failure_reason", "rate_limit_exceeded")
                    status_span.set_attribute("error.type", "RateLimitExceededError")
                    status_span.set_attribute("error.message", exc.message)
                    status_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # 8. Request Reject - Final rejection point
                with tracer.start_as_current_span("request.reject") as reject_span:
                    reject_span.set_attribute("rate_limit.operation", "reject_rate_limit")
                    reject_span.set_attribute("rate_limit.rejected", True)
                    reject_span.set_attribute("error.type", "RateLimitExceededError")
                    reject_span.set_attribute("error.reason", "rate_limit_exceeded")
                    reject_span.set_attribute("error.message", exc.message)
                    reject_span.set_attribute("error.code", "RATE_LIMIT_EXCEEDED")
                    reject_span.set_attribute("rate_limit.retry_after", exc.retry_after)
                    reject_span.set_attribute("http.status_code", 429)
                    reject_span.set_status(Status(StatusCode.ERROR, exc.message))
                
                # Mark main span as error
                main_span.set_attribute("error", True)
                main_span.set_attribute("error.type", "RateLimitExceededError")
                main_span.set_attribute("error.message", exc.message)
                main_span.set_status(Status(StatusCode.ERROR, exc.message))
        
        # Explicit logging to ensure 429 errors appear in OpenSearch
        # Extract auth context from request.state if available
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        processing_time = 0.001  # Minimal time for rate limit errors
        
        log_context = {
            "method": method,
            "path": path,
            "status_code": 429,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_type": "RateLimitExceededError",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "error_message": exc.message,
            "retry_after": exc.retry_after,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        try:
            logger.warning(
                f"{method} {path} - 429 - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        except Exception as log_exc:
            logging.warning(
                f"429 Rate Limit Error: {method} {path} - {exc.message}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=429,
            content={"detail": error_detail.dict()},
            headers={"Retry-After": str(exc.retry_after)}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle request validation errors (422 Unprocessable Entity)."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get correlation ID if available
        correlation_id = get_correlation_id(request)
        
        # Build error messages
        error_messages = []
        for error in exc.errors():
            loc = ".".join(map(str, error["loc"]))
            error_messages.append(f"{loc}: {error['msg']}")
        
        full_message = f"Validation error: {'; '.join(error_messages)}"
        
        # Create detailed trace structure for validation errors
        if tracer:
            with tracer.start_as_current_span("nmt.inference") as main_span:
                main_span.set_attribute("http.method", method)
                main_span.set_attribute("http.route", path)
                main_span.set_attribute("http.status_code", 422)
                if correlation_id:
                    main_span.set_attribute("correlation.id", correlation_id)
                
                # Try to extract partial request details from validation errors
                try:
                    for error in exc.errors():
                        loc = ".".join(map(str, error["loc"]))
                        if "config" in loc.lower() and "serviceId" in loc.lower():
                            # Try to extract serviceId if present in error location
                            pass
                        if "language" in loc.lower():
                            # Language validation error
                            pass
                        if "input" in loc.lower():
                            # Input validation error
                            pass
                except Exception:
                    pass
                
                # Create identity context span (validation happens before context)
                with tracer.start_as_current_span("nmt.identity.context_attached") as identity_span:
                    identity_span.set_attribute("validation.failed", True)
                    identity_span.set_status(Status(StatusCode.ERROR, "Request validation failed"))
                
                # Create policy check span
                with tracer.start_as_current_span("nmt.policy.check") as policy_span:
                    policy_span.set_attribute("policy.status", "REJECTED")
                    policy_span.set_attribute("policy.rejection_reason", "validation_failed")
                    policy_span.set_status(Status(StatusCode.ERROR, "Request validation failed"))
                
                # Create smart routing decision span
                with tracer.start_as_current_span("nmt.smart_routing.decision") as routing_span:
                    routing_span.set_attribute("routing.status", "BLOCKED")
                    routing_span.set_attribute("routing.block_reason", "validation_failed")
                    routing_span.set_status(Status(StatusCode.ERROR, "Request validation failed - routing blocked"))
                
                # Create validation analysis span
                with tracer.start_as_current_span("validation.decision.analyze_errors") as analyze_span:
                    analyze_span.set_attribute("validation.decision", "analyze_validation_errors")
                    analyze_span.set_attribute("validation.error_count", len(exc.errors()))
                    
                    # Categorize errors
                    missing_fields = []
                    invalid_types = []
                    invalid_values = []
                    
                    for idx, error in enumerate(exc.errors()):
                        loc = ".".join(map(str, error["loc"]))
                        error_type = error.get("type", "")
                        error_msg = error.get("msg", "")
                        
                        reject_span.set_attribute(f"validation.error.{idx}.location", loc)
                        reject_span.set_attribute(f"validation.error.{idx}.message", error_msg)
                        reject_span.set_attribute(f"validation.error.{idx}.type", error_type)
                        
                        # Categorize
                        if "missing" in error_type.lower() or "required" in error_msg.lower():
                            missing_fields.append(loc)
                        elif "type" in error_type.lower() or "value_error" in error_type.lower():
                            invalid_types.append(loc)
                        else:
                            invalid_values.append(loc)
                    
                    if missing_fields:
                        analyze_span.set_attribute("validation.missing_fields", ",".join(missing_fields))
                        reject_span.set_attribute("validation.missing_fields", ",".join(missing_fields))
                    if invalid_types:
                        analyze_span.set_attribute("validation.invalid_types", ",".join(invalid_types))
                        reject_span.set_attribute("validation.invalid_types", ",".join(invalid_types))
                    if invalid_values:
                        analyze_span.set_attribute("validation.invalid_values", ",".join(invalid_values))
                        reject_span.set_attribute("validation.invalid_values", ",".join(invalid_values))
                    
                    analyze_span.set_attribute("validation.decision.result", "rejected")
                    analyze_span.set_status(Status(StatusCode.ERROR, full_message))
                
                # Create request.reject span as final rejection point
                with tracer.start_as_current_span("request.reject") as reject_span:
                    reject_span.set_attribute("validation.operation", "reject_validation")
                    reject_span.set_attribute("validation.rejected", True)
                    reject_span.set_attribute("error.type", "RequestValidationError")
                    reject_span.set_attribute("error.reason", "validation_failed")
                    reject_span.set_attribute("error.message", full_message)
                    reject_span.set_attribute("error.code", "VALIDATION_ERROR")
                    reject_span.set_attribute("http.status_code", 422)
                    reject_span.set_attribute("validation.error_count", len(exc.errors()))
                    reject_span.add_event("validation.failed", {
                        "error_count": len(exc.errors()),
                        "message": full_message
                    })
                    reject_span.set_status(Status(StatusCode.ERROR, full_message))
                
                # Mark main span as error
                main_span.set_attribute("error", True)
                main_span.set_attribute("error.type", "RequestValidationError")
                main_span.set_attribute("error.message", full_message)
                main_span.set_status(Status(StatusCode.ERROR, full_message))
        
        # Log the validation error with the SAME format as RequestLoggingMiddleware
        # This ensures 422 errors appear in OpenSearch with consistent format
        # 
        # WHY THIS IS NEEDED:
        # - FastAPI raises RequestValidationError DURING body parsing (before route handler)
        # - Exception handler returns 422 response
        # - Response SHOULD go through RequestLoggingMiddleware, but sometimes doesn't
        # - This explicit logging ensures 422 errors are ALWAYS logged to OpenSearch
        # - This is STANDARD PRACTICE: All HTTP responses (200, 401, 403, 422, 500) should be logged
        #
        # Extract auth context from request.state if available (same as RequestLoggingMiddleware)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # Calculate processing time (approximate, since we don't have start_time)
        # Validation errors happen very quickly (during body parsing)
        processing_time = 0.001  # Minimal time for validation errors
        
        # Build context matching RequestLoggingMiddleware format EXACTLY
        # This ensures 422 errors appear in OpenSearch with the same structure as 401/403/200
        log_context = {
            "method": method,
            "path": path,
            "status_code": 422,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            # Additional validation-specific fields for better debugging
            "validation_errors": exc.errors(),
            "validation_error_count": len(exc.errors()),
            "validation_error_message": full_message,
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        # Log with WARNING level to match RequestLoggingMiddleware for 4xx errors
        # Format: "{method} {path} - {status_code} - {duration}s" (same as RequestLoggingMiddleware)
        # This ensures 422 errors appear in OpenSearch with the same format as 401/403
        # 
        # IMPORTANT: This MUST log because FastAPI's RequestValidationError happens
        # during body parsing, BEFORE the route handler, and the response from this
        # exception handler might not go through RequestLoggingMiddleware properly.
        try:
            logger.warning(
                f"{method} {path} - 422 - {processing_time:.3f}s",
                extra={"context": log_context}
            )
        except Exception as log_exc:
            # Fallback: If structured logging fails, use basic logging
            logging.warning(
                f"422 Validation Error: {method} {path} - {full_message}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message="Validation error",
            code="VALIDATION_ERROR",
            timestamp=time.time(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle generic HTTP exceptions."""
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        correlation_id = get_correlation_id(request)
        status_code = exc.status_code
        
        # Explicit logging to ensure HTTP errors appear in OpenSearch
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        processing_time = 0.001  # Minimal time for HTTP errors
        
        log_context = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_type": "HTTPException",
            "error_code": "HTTP_ERROR",
            "error_message": str(exc.detail),
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        # Log based on status code
        try:
            if 400 <= status_code < 500:
                logger.warning(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context}
                )
            else:
                logger.error(
                    f"{method} {path} - {status_code} - {processing_time:.3f}s",
                    extra={"context": log_context}
                )
        except Exception as log_exc:
            logging.warning(
                f"HTTP Error {status_code}: {method} {path} - {exc.detail}",
                exc_info=log_exc
            )
        
        error_detail = ErrorDetail(
            message=str(exc.detail),
            code="HTTP_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=status_code,
            content={"detail": error_detail.dict()}
        )
    
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        # Extract exception from ExceptionGroup if present (Python 3.11+)
        actual_exc = exc
        try:
            if hasattr(exc, 'exceptions') and exc.exceptions:
                actual_exc = exc.exceptions[0]
        except (AttributeError, IndexError):
            pass
        
        # Check if it's one of our custom exceptions that wasn't caught
        if isinstance(actual_exc, RateLimitExceededError):
            return await rate_limit_error_handler(request, actual_exc)
        elif isinstance(actual_exc, AuthenticationError):
            return await authentication_error_handler(request, actual_exc)
        elif isinstance(actual_exc, AuthorizationError):
            return await authorization_error_handler(request, actual_exc)
        elif isinstance(actual_exc, HTTPException):
            return await http_exception_handler(request, actual_exc)
        
        # Extract request info for logging
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        correlation_id = get_correlation_id(request)
        
        # Explicit logging to ensure 500 errors appear in OpenSearch
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        processing_time = 0.001  # Minimal time for unexpected errors
        
        log_context = {
            "method": method,
            "path": path,
            "status_code": 500,
            "duration_ms": round(processing_time * 1000, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "error_type": type(exc).__name__,
            "error_code": "INTERNAL_ERROR",
            "error_message": str(exc),
        }
        
        if user_id:
            log_context["user_id"] = user_id
        if api_key_id:
            log_context["api_key_id"] = api_key_id
        if correlation_id:
            log_context["correlation_id"] = correlation_id
        
        # Log the error with full traceback
        try:
            logger.error(
                f"{method} {path} - 500 - {processing_time:.3f}s",
                extra={"context": log_context},
                exc_info=True
            )
        except Exception as log_exc:
            logging.error(
                f"500 Internal Error: {method} {path} - {exc}",
                exc_info=True
            )
        
        error_detail = ErrorDetail(
            message="Internal server error",
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content={"detail": error_detail.dict()}
        )
