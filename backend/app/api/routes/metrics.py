from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get(
    "/metrics",
    tags=["system"],
    summary="Prometheus Metrics",
    description=(
        "Expose Prometheus-compatible metrics including request count, latency histograms, "
        "status-code distribution, and active users gauge."
    ),
)
async def get_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
