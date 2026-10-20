from fastapi import APIRouter
from app.core import load_data, get_or_404

router = APIRouter(prefix="/mock/egrul", tags=["mock:egrul"])


@router.get("/{inn}")
async def get_company(inn: str):
    return get_or_404(load_data("egrul"), inn)