import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from PortPilot.api.routes.console import router as console_router
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


app = FastAPI(title="PortPilot Rescheduling Agent", lifespan=lifespan)

# The operations console is a separate origin (Vite dev server, or a static
# bundle on CloudFront), so it needs an explicit CORS grant to read this API
# from a browser. Override with PORTPILOT_CORS_ORIGINS as a comma-separated
# list when serving the console from somewhere else.
_origins = os.getenv(
    "PORTPILOT_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(console_router)
