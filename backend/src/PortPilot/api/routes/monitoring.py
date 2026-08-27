from fastapi import APIRouter
from monitor import monitor_vessels

router = APIRouter()

@router.post("/monitor")
def run_monitor():
    return monitor_vessels()