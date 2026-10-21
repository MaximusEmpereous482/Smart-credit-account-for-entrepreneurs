from fastapi import FastAPI
from app.database import engine, Base
from app import models
from app.api import client # <--- ОБЯЗАТЕЛЬНО ДОЛЖНО БЫТЬ

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MSP Credit Orchestrator",
    version="1.0.0",
)

# <--- ОБЯЗАТЕЛЬНО ДОЛЖНО БЫТЬ
app.include_router(client.router, prefix="/api/client")

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok"}