from fastapi import FastAPI
from PortPilot.api.routes.monitoring import router

app = FastAPI()

app.include_router(router)