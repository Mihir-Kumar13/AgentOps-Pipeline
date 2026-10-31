"""OpenTelemetry setup for traces, metrics and logs.

Telemetry is only exported when OTEL_EXPORTER_OTLP_ENDPOINT is set (for example
http://localhost:4318). Without it the OTel API stays a no-op, so unit tests and
`make eval` keep running offline with no collector.
"""

import atexit
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agent.telemetry.instruments import AGENT_NAME, histogram_views

_enabled = False


def setup_telemetry(service_name: str = AGENT_NAME) -> bool:
    """Install OTLP exporters once. Returns True if telemetry is being exported."""
    global _enabled
    if _enabled or not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return _enabled

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment.name": os.getenv("DEPLOY_ENV", "local"),
        }
    )
    # Exporters read OTEL_EXPORTER_OTLP_ENDPOINT and add /v1/traces etc. themselves.
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000)
        ],
        views=histogram_views(),
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    agent_logger = logging.getLogger("agent")
    agent_logger.setLevel(logging.INFO)
    agent_logger.addHandler(LoggingHandler(logger_provider=logger_provider))

    # Short-lived processes (the eval runner) must flush before exiting.
    def _shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()
        logger_provider.shutdown()

    atexit.register(_shutdown)
    _enabled = True
    return True
