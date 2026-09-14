"""Analytics, charts, and anomaly detection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..ratelimit import rate_limit
from ..services import analytics as analytics_service
from ..services import anomalies as anomalies_service

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)


@router.get("/anomalies")
def get_anomalies():
    return {
        "success": True,
        "data": anomalies_service.detect_anomalies(),
    }


@router.get("/charts")
def get_chart(
    metric: str = Query(default="tasks_by_status"),
    chart_type: str | None = Query(default=None),
    team: str | None = Query(default=None),
):
    return {
        "success": True,
        "data": analytics_service.build_chart_data(
            metric=metric,
            chart_type=chart_type,
            team=team,
        ),
    }
