from fastapi import FastAPI
from app.services import bki, egrul, fns, risk_flags, zsk

app = FastAPI(
    title="MSP Credit Mocks",
    version="1.0.0",
    description="Синтетические мок-сервисы проверок для кредитного конвейера МСП",
)

for module in (egrul, fns, bki, risk_flags, zsk):
    app.include_router(module.router)


@app.get("/health", tags=["system"])
def health():
    """Проверка, что сервер жив"""
    return {"status": "ok", "version": "1.0.0"}