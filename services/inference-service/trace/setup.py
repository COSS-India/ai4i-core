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
                span_data = {
                    "name": span.name,
                    "context": {
                        "trace_id": f"0x{span_context.trace_id:032x}",
                        "span_id": f"0x{span_context.span_id:016x}",
                        "parent_span_id": parent_span_id,
                        "trace_state": str(span_context.trace_state or ""),
                    },
                    "kind": str(span.kind),
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "attributes": dict(span.attributes) if span.attributes else {},
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

    Spans are exported via LoggerSpanExporter (stdout + optional Kafka → OpenSearch).
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        service_name = settings.SERVICE_NAME
        service_version = settings.SERVICE_VERSION
        resource = Resource.create({
            "service.name": service_name,
            "service.version": service_version,
        })

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(LoggerSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        logger.info("✓ OpenTelemetry tracing configured (stdout + Kafka → OpenSearch)")
    except ImportError:
        logger.warning("OpenTelemetry not available, tracing disabled")
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}", exc_info=True)
