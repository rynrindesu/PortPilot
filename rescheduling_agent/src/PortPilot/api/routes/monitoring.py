from datetime import date
from fastapi import APIRouter

from PortPilot.monitoring.monitor_service import monitor_vessels
from PortPilot.monitoring.scheduler import automation_scheduler

router = APIRouter()

@router.post("/monitor")
def run_monitor(arrival_date: date):
    return monitor_vessels(arrival_date.isoformat())


@router.get("/automation/status")
def automation_status():
    """Return schedules and the latest result from each automation job."""

    return automation_scheduler.status
