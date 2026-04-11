from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

_METRICS_CONFIGURED = False


def configure_metrics(app: FastAPI) -> None:
    global _METRICS_CONFIGURED
    if _METRICS_CONFIGURED:
        return

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=False,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
    )
    instrumentator.instrument(app)

    _METRICS_CONFIGURED = True
