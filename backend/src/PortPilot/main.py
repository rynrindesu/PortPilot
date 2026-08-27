from fastapi import FastAPI
from portpilot.api.routes.monitoring import router

app = FastAPI()

app.include_router(router)