import logging
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import SessionLocal
from app import models
from app.core import mocks_client

logger = logging.getLogger(__name__)


def save_check(db: Session, app_id: int, check_type: str, status: str, raw_response: dict):
    """Сохраняет результат проверки в БД"""
    check = models.CheckResult(
        application_id=app_id,
        check_type=check_type,
        execution_status=status,
        raw_response=raw_response
    )
    db.add(check)
    db.commit()


def update_status(db: Session, app: models.Application, new_status: str, step_name: str, actor: str = "SYSTEM"):
    """Меняет статус заявки и пишет в аудит"""
    old_status = app.status
    app.status = new_status
    app.current_step_name = step_name

    audit = models.AuditEvent(
        application_id=app.id,
        actor=actor,
        action=f"STATUS_CHANGED_TO_{new_status}",
        old_status=old_status,
        new_status=new_status
    )
    db.add(audit)
    db.commit()
    db.refresh(app)
    logger.info(f"Заявка {app.id}: {old_status} -> {new_status} ({step_name})")


def make_decision(db: Session, app: models.Application, decision_type: str, reason: str, amount: float = None):
    """Сохраняет финальное решение"""
    app.status = decision_type
    app.current_step_name = "Решение принято"

    decision = models.Decision(
        application_id=app.id,
        decision_type=decision_type,
        reason_text=reason,
        approved_amount=amount if amount else app.requested_amount,
        approved_term_months=app.requested_term_months,
        approved_rate=18.5,  # Демо-ставка
        decided_by="SYSTEM"
    )
    db.add(decision)
    db.commit()
    db.refresh(app)
    logger.info(f"Заявка {app.id}: Решение {decision_type} ({reason})")


async def run_pipeline(application_id: int):
    """Главный конвейер. Запускается в фоне после отправки заявки."""
    db = SessionLocal()
    try:
        app = db.query(models.Application).filter(models.Application.id == application_id).first()
        if not app:
            return

        inn = app.company.inn

        # ==========================================
        # ШАГ 1: Стоп-факторы (ЕГРЮЛ)
        # ==========================================
        update_status(db, app, "STOP_CHECKS", "Проверка ЕГРЮЛ")
        egrul = await mocks_client.get_egrul(inn)

        if "__error__" in egrul:
            save_check(db, app.id, "egrul", "FAILED", egrul)
            return make_decision(db, app, "MANUAL_REVIEW", "Техническая ошибка при проверке ЕГРЮЛ")

        save_check(db, app.id, "egrul", "SUCCESS", egrul)

        if egrul.get("status") != "ACTIVE" or egrul.get("has_unreliable_records") or egrul.get("management", [{}])[
            0].get("disqualified"):
            return make_decision(db, app, "REJECTED", "Стоп-фактор: Бизнес ликвидирован или директор дисквалифицирован")

        # ==========================================
        # ШАГ 2: Стоп-факторы (ЗСК ЦБ)
        # ==========================================
        update_status(db, app, "STOP_CHECKS", "Проверка ЗСК ЦБ")
        zsk = await mocks_client.get_zsk(inn)

        if "__error__" in zsk:
            save_check(db, app.id, "zsk", "FAILED", zsk)
            return make_decision(db, app, "MANUAL_REVIEW", "Техническая ошибка при проверке ЗСК")

        save_check(db, app.id, "zsk", "SUCCESS", zsk)

        if zsk.get("zone") == "RED":
            return make_decision(db, app, "REJECTED",
                                 "Стоп-фактор: Красная зона ЗСК (подозрение на сомнительные операции)")

        # ==========================================
        # ШАГ 3: Согласие и БКИ
        # ==========================================
        if not app.bki_consent_granted:
            update_status(db, app, "WAITING_CONSENT", "Ожидание согласия на БКИ")
            return

        update_status(db, app, "RISK_CHECKS", "Проверка кредитной истории (БКИ)")
        bki = await mocks_client.get_bki(inn, consent_id=f"CNT-2026-{inn[-4:]}")

        if "__error__" in bki:
            save_check(db, app.id, "bki", "FAILED", bki)
            return make_decision(db, app, "MANUAL_REVIEW", "БКИ недоступно, требуется ручная проверка")

        save_check(db, app.id, "bki", "SUCCESS", bki)

        if bki.get("score") is None:
            return make_decision(db, app, "MANUAL_REVIEW", "Нет кредитной истории")

        if bki.get("delinquency", {}).get("max_overdue_days", 0) >= 60:
            return make_decision(db, app, "REJECTED", "Критические просрочки в прошлом (более 60 дней)")

        # ==========================================
        # ШАГ 4: ФНС и Риски
        # ==========================================
        update_status(db, app, "RISK_CHECKS", "Проверка финансов и судебных рисков")

        fns = await mocks_client.get_fns(inn)
        risk = await mocks_client.get_risk_flags(inn)

        save_check(db, app.id, "fns", "SUCCESS" if "__error__" not in fns else "FAILED", fns)
        save_check(db, app.id, "risk_flags", "SUCCESS" if "__error__" not in risk else "FAILED", risk)

        if risk.get("verdict") == "HIGH_RISK":
            return make_decision(db, app, "REJECTED", "Высокий судебный риск или банкротство")

        if fns.get("taxes", {}).get("arrears", {}).get("oldest_days", 0) > 30:
            return make_decision(db, app, "MANUAL_REVIEW", "Есть налоговая задолженность")

        # ==========================================
        # ШАГ 5: Скоринг и финальное решение
        # ==========================================
        update_status(db, app, "SCORING", "Расчет скоринга")

        # Простая логика: если БКИ HIGH_RISK, даем counter-offer (меньше сумма)
        if bki.get("score", {}).get("band") == "HIGH_RISK":
            new_amount = app.requested_amount * 0.5
            return make_decision(db, app, "COUNTER_OFFER", "Снижена сумма из-за высокого риска", amount=new_amount)

        # Если все проверки пройдены - одобряем
        make_decision(db, app, "APPROVED", "Все проверки пройдены успешно")

    except Exception as e:
        logger.error(f"Ошибка в конвейере для заявки {application_id}: {str(e)}")
        db.rollback()
    finally:
        db.close()