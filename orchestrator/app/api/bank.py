from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app import models, schemas
from app.core.pipeline import make_decision  # Импортируем логику решения

router = APIRouter()


# Схема для ручного решения
class ManualDecisionRequest(BaseModel):
    decision_type: str  # "APPROVED" or "REJECTED"
    reason: str


@router.get("/applications", response_model=List[schemas.ApplicationDetailResponse], tags=["Bank"])
def get_all_applications(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Получить список всех заявок (с возможностью фильтрации по статусу)"""
    query = db.query(models.Application)
    if status:
        query = query.filter(models.Application.status == status)
    # Сортируем по дате создания (сначала новые)
    return query.order_by(models.Application.created_at.desc()).all()


@router.post("/applications/{application_id}/manual-decision", tags=["Bank"])
def make_manual_decision(
        application_id: int,
        req: ManualDecisionRequest,
        db: Session = Depends(get_db)
):
    """Принять ручное решение по заявке (например, которая висит в MANUAL_REVIEW)"""
    app = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if app.status not in ["MANUAL_REVIEW", "SUBMITTED", "SCORING"]:
        raise HTTPException(status_code=400, detail="По этой заявке уже принято решение")

    # Используем функцию из pipeline, но с другим актором
    make_decision(
        db, app,
        decision_type=req.decision_type,
        reason=req.reason,
        amount=app.requested_amount if req.decision_type == "APPROVED" else None
    )

    # Перезаписываем actor в решении на сотрудника банка
    decision = db.query(models.Decision).filter(models.Decision.application_id == app.id).first()
    if decision:
        decision.decided_by = "BANK_EMPLOYEE"
        db.commit()

    return {"message": "Решение успешно принято", "status": app.status}