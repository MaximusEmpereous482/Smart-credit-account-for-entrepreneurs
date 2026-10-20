from fastapi import APIRouter
from app.core import load_data, get_or_404

router = APIRouter(prefix="/mock/zsk", tags=["mock:zsk"])


@router.get("/{inn}")
async def get_zsk(inn: str):
    return get_or_404(load_data("zsk"), inn)