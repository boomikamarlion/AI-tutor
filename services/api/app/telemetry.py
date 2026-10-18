import logging

from app.config import get_settings


def setup_telemetry(service_name: str) -> None:
    """Send traces, logs and metrics to Application Insights when a connection string is set."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    conn = get_settings().applicationinsights_connection_string
    if not conn:
        return
    import os

    from azure.monitor.opentelemetry import configure_azure_monitor

    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    configure_azure_monitor(connection_string=conn)
