from datetime import date
from fastapi import APIRouter
from PortPilot.monitoring.monitor_service import monitor_vessels

router = APIRouter()

@router.post("/monitor")
def run_monitor(arrival_date: date):
    return monitor_vessels(arrival_date.isoformat())