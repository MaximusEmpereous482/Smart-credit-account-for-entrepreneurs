from fastapi import APIRouter, Header, HTTPException
from app.core import load_data, get_or_404

router = APIRouter(prefix="/mock/bki", tags=["mock:bki"])


@router.get("/{inn}")
async def get_bki(inn: str, x_consent_id: str | None = Header(default=None)):
    report = get_or_404(load_data("bki"), inn)

    if not report.get("consent", {}).get("granted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CONSENT_REQUIRED",
                "message": "Нет согласия субъекта на запрос кредитной истории",
            },
        )
    if x_consent_id and report["consent"].get("consent_id") != x_consent_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CONSENT_MISMATCH",
                "message": "consent_id не совпадает с зарегистрированным",
            },
        )
    return report