import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from PortPilot.api.routes.documents import router as documents_router
from PortPilot.api.routes.compliance_demo import router as compliance_demo_router
from PortPilot.api.routes.port_calls import router as port_calls_router
from PortPilot.api.routes.agent import router as agent_router
from PortPilot.api.routes.console import router as console_router
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="PortPilot Port-Ops Agent")

# The operations console runs on its own origin and reads this API from the
# browser, so it needs an explicit CORS grant.
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

app.include_router(documents_router)
app.include_router(compliance_demo_router)
app.include_router(port_calls_router)
app.include_router(agent_router)
app.include_router(console_router)


@app.get("/")
def root():
    return {
        "name": "PortPilot",
        "status": "running",
    }
