from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.core.pipeline import run_pipeline  # <-- Импортируем наш мозг

router = APIRouter()


@router.post("/applications", response_model=schemas.ApplicationResponse, tags=["Client"])
def create_application(app_in: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    company = db.query(models.Company).filter(models.Company.inn == app_in.client_inn).first()
    if not company:
        company = models.Company(
            inn=app_in.client_inn,
            company_name=f"Компания {app_in.client_inn}",
            entity_type="LEGAL_ENTITY"
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    new_app = models.Application(
        company_id=company.id,
        product_code=app_in.product_code,
        requested_amount=app_in.requested_amount,
        requested_term_months=app_in.requested_term_months,
        purpose=app_in.purpose,
        bki_consent_granted=app_in.bki_consent_granted,
        status="DRAFT",
        current_step_name="Черновик"
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return new_app


@router.post("/applications/{application_id}/submit", tags=["Client"])
async def submit_application(
        application_id: int,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    app = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if app.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Заявку можно отправить только из статуса DRAFT")

    app.status = "SUBMITTED"
    app.current_step_name = "Заявка отправлена, ожидает проверок"
    db.commit()

    # Запускаем НАСТОЯЩИЙ конвейер в фоне
    background_tasks.add_task(run_pipeline, application_id)

    return {"message": "Заявка отправлена в обработку", "status": app.status}


@router.get("/applications/{application_id}", response_model=schemas.ApplicationDetailResponse, tags=["Client"])
def get_application(application_id: int, db: Session = Depends(get_db)):
    app = db.query(models.Application).filter(models.Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return app
