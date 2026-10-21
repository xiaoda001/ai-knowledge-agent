"""Opt-in OpenTelemetry setup shared by the API and Celery worker."""

import logging
import os

logger = logging.getLogger(__name__)


def _sanitize_http_span(span, _scope) -> None:
    # Inbound URLs can carry secrets or user supplied search terms. Keep route
    # templates/status/method from instrumentation, but blank concrete URLs.
    if span and span.is_recording():
        for key in ("url.query", "url.full", "http.url", "http.target"):
            span.set_attribute(key, "")


def _sanitize_redis_span(span, _connection, args, _kwargs) -> None:
    # Redis arguments may contain document IDs, serialized payloads, or secrets.
    # Preserve only the command name; remove the generated statement attribute.
    if span and span.is_recording():
        if args:
            span.set_attribute("db.operation.name", str(args[0]).upper())
        for key in ("db.statement", "db.query.text"):
            span.set_attribute(key, "")


def configure_observability(*, app=None, engine=None, celery_app=None) -> bool:
    """Configure OTLP tracing/metrics when OTEL_ENABLED is true.

    The application remains available if telemetry dependencies or the collector
    are unavailable. Instrumentation deliberately does not capture request bodies,
    headers, prompts, retrieved text, or user identifiers.
    """
    if os.getenv("OTEL_ENABLED", "false").strip().lower() != "true":
        return False

    if celery_app is not None and app is None:
        # Celery preforks workers. Create SDK exporters and instrumentors inside
        # each child process, after fork, so exporter threads are never inherited.
        try:
            from celery.signals import worker_process_init

            @worker_process_init.connect(weak=False)
            def _initialize_worker_telemetry(**_kwargs):
                _configure_runtime(celery_app=celery_app)

            return True
        except Exception as exc:
            logger.warning("OpenTelemetry worker hook unavailable (%s)", type(exc).__name__)
            return False

    return _configure_runtime(app=app, engine=engine, celery_app=celery_app)


def _configure_runtime(*, app=None, engine=None, celery_app=None) -> bool:
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
        service_name = os.getenv("OTEL_SERVICE_NAME", "knowledge-api" if app else "knowledge-worker")
        resource = Resource.create({"service.name": service_name})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")),
        ))
        trace.set_tracer_provider(tracer_provider)
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")),
            export_interval_millis=15000,
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(
                app, tracer_provider=tracer_provider,
                server_request_hook=_sanitize_http_span,
            )
        if engine is not None:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
        if celery_app is not None:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor
            CeleryInstrumentor().instrument(tracer_provider=tracer_provider)
        if app is not None or celery_app is not None:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument(
                tracer_provider=tracer_provider,
                request_hook=_sanitize_redis_span,
            )

        _configure_log_export(resource, endpoint)

        return True
    except Exception as exc:
        # Never prevent the API or worker from starting because telemetry failed.
        logger.warning("OpenTelemetry setup unavailable (%s)", type(exc).__name__)
        return False


def _configure_log_export(resource, endpoint: str) -> None:
    """Export standard-library logs to OTLP while retaining console logging."""
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=endpoint, insecure=endpoint.startswith("http://")),
    ))
    set_logger_provider(provider)

    root_logger = logging.getLogger()
    if not any(isinstance(handler, LoggingHandler) for handler in root_logger.handlers):
        root_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)


def tracer(name: str):
    from opentelemetry import trace
    return trace.get_tracer(name)
