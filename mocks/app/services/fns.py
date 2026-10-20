from fastapi import APIRouter
from app.core import load_data, get_or_404

router = APIRouter(prefix="/mock/fns", tags=["mock:fns"])


@router.get("/{inn}")
async def get_fns(inn: str):
    return get_or_404(load_data("fns"), inn)