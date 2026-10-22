from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app import models
from app.api import client

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MSP Credit Orchestrator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Для хакатона разрешаем всем
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# <--- ОБЯЗАТЕЛЬНО ДОЛЖНО БЫТЬ
app.include_router(client.router, prefix="/api/client")

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok"}
