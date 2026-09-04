from fastapi import FastAPI
from PortPilot.api.routes.monitoring import router as monitoring_router
from PortPilot.api.routes.documents import router as documents_router
from PortPilot.api.routes.compliance_demo import router as compliance_demo_router
from PortPilot.api.routes.port_calls import router as port_calls_router
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.include_router(monitoring_router)
app.include_router(documents_router)
app.include_router(compliance_demo_router)
app.include_router(port_calls_router)

@app.get("/")
def root():
    return {
        "name": "PortPilot",
        "status": "running",
    }