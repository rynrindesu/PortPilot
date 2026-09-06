from fastapi import FastAPI
from PortPilot.api.routes.monitoring import router as monitoring_router
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.include_router(monitoring_router)

@app.get("/")
def root():
    return {
        "name": "PortPilot",
        "status": "running",
    }