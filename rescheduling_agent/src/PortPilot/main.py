import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from PortPilot.api.routes.monitoring import router
from PortPilot.monitoring.scheduler import automation_scheduler


def _automation_enabled() -> bool:
    return os.getenv("PORTPILOT_AUTOMATION_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    automation_enabled = _automation_enabled()
    if automation_enabled:
        await automation_scheduler.start()
    try:
        yield
    finally:
        if automation_enabled:
            await automation_scheduler.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(router)
