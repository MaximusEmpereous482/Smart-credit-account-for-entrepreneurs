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
    """Принять ручное решение по заявке (обновляет существующее или создает новое)"""
    app = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if app.status in ["APPROVED", "REJECTED", "COUNTER_OFFER"] and app.decision:
        raise HTTPException(status_code=400, detail="По этой заявке уже принято финальное решение")

    final_amount = app.requested_amount if req.decision_type == "APPROVED" else None
    final_term = app.requested_term_months if req.decision_type == "APPROVED" else None
    final_rate = 18.5 if req.decision_type == "APPROVED" else None

    decision = db.query(models.Decision).filter(models.Decision.application_id == app.id).first()

    if decision:

        decision.decision_type = req.decision_type
        decision.approved_amount = final_amount
        decision.approved_term_months = final_term
        decision.approved_rate = final_rate
        decision.reason_code = "MANUAL_OVERRIDE"
        decision.reason_text = req.reason
        decision.decided_by = "BANK_EMPLOYEE"
    else:

        decision = models.Decision(
            application_id=app.id,
            decision_type=req.decision_type,
            approved_amount=final_amount,
            approved_term_months=final_term,
            approved_rate=final_rate,
            reason_code="MANUAL_DECISION",
            reason_text=req.reason,
            decided_by="BANK_EMPLOYEE"
        )
        db.add(decision)

    old_status = app.status
    app.status = req.decision_type
    app.current_step_name = "Решение принято сотрудником банка"

    audit = models.AuditEvent(
        application_id=app.id,
        actor="BANK_EMPLOYEE",
        action=f"MANUAL_DECISION_{req.decision_type}",
        old_status=old_status,
        new_status=req.decision_type,
        details={"reason": req.reason}
    )
    db.add(audit)

    db.commit()
    db.refresh(app)

    return {"message": "Решение успешно принято", "status": app.status}