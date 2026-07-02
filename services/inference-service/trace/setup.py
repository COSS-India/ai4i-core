import logging
import json

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from config import settings

logger = logging.getLogger(__name__)


class LoggerSpanExporter(SpanExporter):
    """
    Custom span exporter that sends span data to Python logger and Kafka.
    Outputs spans as structured JSON via logger.info() and publishes to a Kafka topic
    for downstream consumption by FluentBit → OpenSearch.
    """

    KAFKA_TOPIC = settings.KAFKA_TOPIC_OTEL_TRACE

    def __init__(self):
        self._producer = None
        self._kafka_enabled = False
        if settings.KAFKA_ENABLED:
            self._init_kafka()
        else:
            logger.info(
                "Kafka span export disabled (KAFKA_ENABLED=false); "
                "spans logged to stdout only."
            )

    def _init_kafka(self):
        """Initialize Kafka producer for span export."""
        try:
            from kafka import KafkaProducer
            bootstrap_servers = settings.KAFKA_SERVER
            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks="all",
                retries=3,
                max_block_ms=5000,
            )
            self._kafka_enabled = True
            logger.info(f"✓ Kafka span exporter initialized: topic={self.KAFKA_TOPIC}, servers={bootstrap_servers}")
        except Exception as e:
            logger.warning(f"Kafka producer init failed, spans will only be logged: {e}")
            self._kafka_enabled = False

    def export(self, spans):
        for span in spans:
            try:
                span_context = span.get_span_context()
                parent_span_id = (
                    f"0x{span.parent.span_id:016x}" if span.parent else None
                )
                # correlation_id was stored as a span attribute by get_context_attributes()
                # while still in request context. Reading it here (background thread,
                # request context gone) is the only safe path — get_trace_id() returns None.
                span_attrs = dict(span.attributes) if span.attributes else {}
                correlation_id = span_attrs.get("correlation_id")
                otel_trace_id = f"0x{span_context.trace_id:032x}"
                span_data = {
                    "name": span.name,
                    "context": {
                        "trace_id": correlation_id or otel_trace_id,
                        "otel_trace_id": otel_trace_id,
                        "span_id": f"0x{span_context.span_id:016x}",
                        "parent_span_id": parent_span_id,
                        "trace_state": str(span_context.trace_state or ""),
                    },
                    "kind": str(span.kind),
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "attributes": span_attrs,
                    "status": {
                        "status_code": str(span.status.status_code),
                        "description": span.status.description,
                    },
                }

                # Log to Python logger
                logger.info(json.dumps(span_data, default=str))

                # Push to Kafka
                if self._kafka_enabled and self._producer:
                    self._producer.send(self.KAFKA_TOPIC, value=span_data)

            except Exception as e:
                logger.debug(f"Failed to export span: {e}")

        # Flush Kafka buffer
        if self._kafka_enabled and self._producer:
            try:
                self._producer.flush(timeout=5)
            except Exception as e:
                logger.debug(f"Kafka flush failed: {e}")

        return SpanExportResult.SUCCESS

    def shutdown(self):
        if self._producer:
            try:
                self._producer.flush(timeout=10)
                self._producer.close()
            except Exception:
                # Best-effort flush during process exit — Kafka may already be
                # unreachable; spans are still on stdout via the logger.
                pass

    def force_flush(self, timeout_millis=None):
        if self._producer:
            try:
                self._producer.flush(timeout=(timeout_millis or 5000) / 1000)
            except Exception:
                # Best-effort flush — see shutdown(); never block span export.
                pass
        return True

def setup_tracing() -> None:
    """
    Initialize OpenTelemetry tracing for inference service.

    Sets up the tracer that will be used throughout the service
    for distributed tracing of inference requests.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        # Create resource for this service
        service_name = settings.SERVICE_NAME
        service_version = settings.SERVICE_VERSION
        resource = Resource.create({"service.name": service_name, "service.version": service_version})

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Create OTLP exporter (endpoint from settings / OTEL_EXPORTER_OTLP_ENDPOINT)
        otlp_exporter = None
        try:
            endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True,  # Set to False if using TLS
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(LoggerSpanExporter()))
            logger.info("✓ OpenTelemetry tracing configured with Logger exporter")
        except Exception as e:
            logger.warning(f"Could not configure OTLP exporter: {e}")
            logger.info("Tracing will use default span processor")

        # Set the global tracer provider
        trace.set_tracer_provider(tracer_provider)

         # Wrap exporter with filtering to reduce noise (filter out http receive/send spans)
        # Always include send/receive spans for inference service for detailed breakdown
        if otlp_exporter is not None:
            exporter = FilteringSpanExporter(otlp_exporter, service_name=service_name)

            # Add span processors
            # First add organization processor to add org attribute to all spans
            # organization_processor = OrganizationSpanProcessor()
            # tracer_provider.add_span_processor(organization_processor)

            # Then add batch processor for exporting (with filtering exporter)
            span_processor = BatchSpanProcessor(exporter)
            tracer_provider.add_span_processor(span_processor)

        # Get tracer
        tracer = trace.get_tracer(service_name)
        logger.info(f"✅ Tracing initialized for tracer: {tracer}")
        logger.info("✓ Global tracer provider initialized")

    except ImportError:
        logger.warning("OpenTelemetry not available, tracing disabled")
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}", exc_info=True)


class FilteringSpanExporter(SpanExporter):
    """
    Span exporter wrapper that filters out noisy spans like http receive/send.

    These spans are created by FastAPI instrumentation for ASGI operations
    and can clutter traces. This exporter filters them out before exporting.

    Exception: Always includes send/receive spans for inference-service
    to provide detailed request/response breakdown.
    """

    # Spans to filter out (by name pattern)
    # These are created by ASGI instrumentation and create noise in traces
    FILTERED_SPAN_NAMES = [
        "http receive",
        "http send",
        " http receive",  # With leading space (common in ASGI spans)
        " http send",     # With leading space
    ]

    def __init__(self, base_exporter: SpanExporter, service_name: str = None):
        """Initialize the filtering exporter with a base exporter."""
        self.base_exporter = base_exporter
        self.service_name = service_name
        # Always include send/receive spans for inference service
        self.include_send_receive = service_name == "inference-service"

    def export(self, spans):
        """Export spans, filtering out noisy ones."""
        if not spans:
            return SpanExportResult.SUCCESS

        # Filter out spans matching filtered patterns
        filtered_spans = []
        filtered_count = 0
        # For API gateway, de‑duplicate http send/receive spans with the same name
        seen_http_span_names = set()
        for span in spans:
            span_name = span.name.lower() if span.name else ""
            should_filter = False

            # Always include send/receive spans for inference service
            if self.include_send_receive:
                # For inference service, enhance send/receive spans with more details,
                # but only keep a single http send/receive span per unique span name
                if any(filtered_name.strip() in span_name for filtered_name in self.FILTERED_SPAN_NAMES):
                    original_name = span.name or span_name
                    if original_name in seen_http_span_names:
                        # Skip duplicate http send/receive span for the same operation
                        continue
                    seen_http_span_names.add(original_name)
                    self._enhance_api_gateway_span(span)
                filtered_spans.append(span)
                continue

            # For other services, filter out send/receive spans
            # Check if span name ends with or contains any of the filtered patterns
            # ASGI spans typically have format: "service-name METHOD /path http receive/send"
            for filtered_name in self.FILTERED_SPAN_NAMES:
                filtered_lower = filtered_name.lower().strip()
                # Check if span name ends with the pattern or contains it
                if span_name.endswith(filtered_lower) or filtered_lower in span_name:
                    should_filter = True
                    filtered_count += 1
                    break

            if not should_filter:
                filtered_spans.append(span)

        # Log filtering stats (only if we filtered something and debug is enabled)
        if filtered_count > 0:
            logger.debug(f"Filtered out {filtered_count} noisy spans (http receive/send)")
        elif self.include_send_receive:
            logger.debug(f"Including all spans for {self.service_name} (including send/receive)")

        # Export filtered spans
        if filtered_spans:
            return self.base_exporter.export(filtered_spans)
        else:
            return SpanExportResult.SUCCESS

    def _enhance_api_gateway_span(self, span):
        """Add detailed attributes to API gateway send/receive spans for better breakdown."""
        try:
            # Extract operation details from span name
            span_name = span.name or ""

            # Add span type attribute
            if "http receive" in span_name.lower():
                span.set_attribute("span.type", "http.receive")
                span.set_attribute("span.phase", "request")
            elif "http send" in span_name.lower():
                span.set_attribute("span.type", "http.send")
                span.set_attribute("span.phase", "response")

            # Try to extract HTTP method and path from span name
            # Format: "api-gateway-service METHOD /path http receive/send"
            parts = span_name.split()
            if len(parts) >= 3:
                method = parts[1] if parts[1] in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"] else None
                if method:
                    span.set_attribute("http.method_extracted", method)
                if len(parts) >= 3:
                    path = parts[2] if parts[2].startswith("/") else None
                    if path:
                        span.set_attribute("http.path_extracted", path)
        except Exception as e:
            # Silently fail if enhancement fails
            logger.debug(f"Failed to enhance API gateway span: {e}")