from fastapi import APIRouter
from app.core import load_data, get_or_404

router = APIRouter(prefix="/mock/risk-flags", tags=["mock:risk_flags"])


@router.get("/{inn}")
async def get_flags(inn: str):
    return get_or_404(load_data("risk_flags"), inn)
