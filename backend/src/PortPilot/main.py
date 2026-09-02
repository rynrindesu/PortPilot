from fastapi import FastAPI
from PortPilot.api.routes.monitoring import router as monitoring_router
from PortPilot.api.routes.documents import router as documents_router

app = FastAPI()

app.include_router(monitoring_router)
app.include_router(documents_router)

@app.get("/")
def root():
    return {
        "name": "PortPilot",
        "status": "running",
    }