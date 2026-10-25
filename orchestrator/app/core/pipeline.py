import logging
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import SessionLocal
from app import models
from app.core import mocks_client

logger = logging.getLogger(__name__)


def save_check(db: Session, app_id: int, check_type: str, status: str, raw_response: dict):
    is_error = "__error__" in raw_response
    execution_status = "FAILED" if is_error else "SUCCESS"

    error_msg = None
    if is_error:
        error_code = raw_response.get("__error__")
        if error_code == "CONSENT_REQUIRED":
            error_msg = "Клиент не дал согласие на запрос кредитной истории (БКИ)"
        elif error_code == "TIMEOUT":
            error_msg = "Сервис не ответил вовремя (превышен таймаут)"
        elif error_code == "HTTP_ERROR":
            error_msg = f"Ошибка HTTP {raw_response.get('status_code')}"
        elif error_code == "FORBIDDEN":
            error_msg = "Доступ запрещен (нет прав или согласия)"
        else:
            error_msg = "Неизвестная ошибка при запросе к внешнему сервису"

    check = models.CheckResult(
        application_id=app_id,
        check_type=check_type,
        execution_status=execution_status,
        error_message=error_msg,
        raw_response=raw_response
    )
    db.add(check)
    db.commit()


def update_status(db: Session, app: models.Application, new_status: str, step_name: str, actor: str = "SYSTEM"):
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


def calculate_loan_terms(score: int, requested_amount: float, term_months: int) -> dict:
    """Глубокая дифференциация (Risk-Based Pricing)"""

    if score >= 90:
        rate, penalty, fee, amount, tier = 14.0, 0.1, 0.0, requested_amount, "A+ (Премиум)"
    elif score >= 80:
        rate, penalty, fee, amount, tier = 17.5, 0.1, 0.0, requested_amount, "A (Стандарт+)"
    elif score >= 70:
        rate, penalty, fee, amount, tier = 21.0, 0.3, 0.0, requested_amount, "B (Базовый)"
    elif score >= 60:
        rate, penalty, fee, amount, tier = 23.5, 0.5, 1.0, requested_amount * 0.7, "C (Рискованный, 70% суммы)"
    else:
        return {"rate": None, "penalty": None, "fee": None, "amount": 0, "payment": None, "tier": "D (Отказ)"}

    # Расчет аннуитетного платежа
    monthly_rate = rate / 100 / 12
    if monthly_rate > 0:
        payment = amount * monthly_rate / (1 - (1 + monthly_rate) ** -term_months)
    else:
        payment = amount / term_months

    return {
        "rate": rate, "penalty": penalty, "fee": fee,
        "amount": amount, "payment": round(payment, 2), "tier": tier
    }


def make_decision(db: Session, app: models.Application, decision_type: str, reason: str, amount: float = None,
                  reason_code: str = "GENERAL", score: int = 0):
    app.status = decision_type
    app.current_step_name = "Решение принято"

    if decision_type in ["REJECTED", "MANUAL_REVIEW"]:
        terms = {"rate": None, "penalty": None, "fee": None, "amount": None, "payment": None}
        product_info = ""
    else:
        # Считаем условия на основе скоринга
        terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)

        # Подбираем название продукта
        product_type_ru = "Универсальный кредит"
        if app.purpose == "EQUIPMENT":
            product_type_ru = "Целевой кредит на оборудование"
        elif app.purpose == "WORKING_CAPITAL":
            product_type_ru = "Овердрафт / Кредитная линия"
        elif app.purpose == "REAL_ESTATE":
            product_type_ru = "Инвестиционный кредит (недвижимость)"
        product_info = f" Рекомендуемый продукт: {product_type_ru}."

        # Если это контроффер, берем урезанную сумму из terms
        if decision_type == "COUNTER_OFFER":
            amount = terms["amount"]

    decision = models.Decision(
        application_id=app.id,
        decision_type=decision_type,
        reason_code=reason_code,
        reason_text=f"{reason}.{product_info}".strip(),
        approved_amount=amount if amount else terms["amount"],
        approved_term_months=app.requested_term_months if decision_type not in ["REJECTED", "MANUAL_REVIEW"] else None,
        approved_rate=terms["rate"],
        penalty_rate=terms["penalty"],
        issuance_fee_percent=terms["fee"],
        monthly_payment=terms["payment"],
        decided_by="SYSTEM"
    )
    db.add(decision)

    audit = models.AuditEvent(
        application_id=app.id,
        actor="SYSTEM",
        action=f"DECISION_{decision_type}",
        old_status=app.status,
        new_status=decision_type,
        details={"reason_code": reason_code, "reason_text": reason}
    )
    db.add(audit)
    db.commit()
    logger.info(f"Заявка {app.id}: Решение {decision_type} ({reason})")


def calculate_scoring(egrul, zsk, bki, fns, risk) -> tuple[int, str]:
    """Точная реализация модели БА (от 0 до 100 баллов)"""
    score = 0

    # МГНОВЕННЫЙ ОТКАЗ (СТОП-ФАКТОРЫ)
    founders = egrul.get("founders", [])
    bankrupt_founders = risk.get("bankrupt_founders", [])
    for founder in founders:
        if founder.get("inn") in bankrupt_founders:
            return 0, "Стоп-фактор: Учредитель находится в стадии банкротства"

    if "__error__" in bki:
        return 0, "Стоп-фактор: Нет согласия на запрос кредитной истории (БКИ)"

    if egrul.get("status") != "ACTIVE":
        return 0, "Стоп-фактор: Компания ликвидирована или в процессе банкротства"

    if fns.get("blocked_accounts"):
        return 0, "Стоп-фактор: Наличие действующих блокировок расчетных счетов"

    if risk.get("verdict") == "HIGH_RISK":
        return 0, "Стоп-фактор: Банкротство бенефициара или критические судебные риски"

    if bki.get("delinquency", {}).get("max_overdue_days", 0) > 90:
        return 0, "Стоп-фактор: Текущие просрочки более 90 дней"

    if egrul.get("has_unreliable_records") or egrul.get("management", [{}])[0].get("disqualified"):
        return 0, "Стоп-фактор: Недостоверные сведения или дисквалификация директора"

    # 1. СТАБИЛЬНОСТЬ БИЗНЕСА (до 10)
    age = egrul.get("age_months", 0)
    if age > 24:
        score += 10
    elif 6 <= age <= 24:
        score += 5

    # 2. ФИНАНСОВОЕ ЗДОРОВЬЕ (до 25)
    fin = fns.get("financials", {}).get("years", [{}])[0]
    profit = fin.get("net_profit", 0)
    revenue = fin.get("revenue", 1)
    is_growing = fin.get("is_growing", False)

    if profit > 0 and is_growing:
        score += 25
    elif profit > 0 and not is_growing:
        score += 15

    # 3. КРЕДИТНАЯ НАГРУЗКА (до 25)
    monthly_revenue = revenue / 12
    monthly_payment = bki.get("total_monthly_payment", 0)
    dti = (monthly_payment / monthly_revenue) if monthly_revenue > 0 else 1.0

    if dti < 0.20:
        score += 25
    elif 0.20 <= dti <= 0.40:
        score += 15

    # 4. НАЛОГОВАЯ ДИСЦИПЛИНА (до 15)
    arrears_amount = fns.get("taxes", {}).get("arrears", {}).get("amount", 0)
    if arrears_amount == 0:
        score += 15
    elif arrears_amount < 10000:
        score += 5

    # 5. СУДЕБНЫЕ РИСКИ (до 10)
    cases = risk.get("sources", {}).get("arbitration_cases", {}).get("as_defendant", 0)
    if cases <= 2:
        score += 10
    elif 3 <= cases <= 5:
        score += 5

    # 6. НАДЕЖНОСТЬ БЕНЕФИЦИАРА (до 15)
    director_score = bki.get("director_bki_score", 0)
    if director_score > 700:
        score += 15
    elif 600 <= director_score <= 700:
        score += 5

    return score, ""


async def run_pipeline(application_id: int):
    db = SessionLocal()
    try:
        app = db.query(models.Application).filter(models.Application.id == application_id).first()
        if not app: return
        inn = app.company.inn

        update_status(db, app, "DATA_ENRICHMENT", "Сбор данных из внешних источников")

        egrul = await mocks_client.get_egrul(inn)

        if "__error__" not in egrul:
            company = app.company
            company.company_name = egrul.get("short_name", company.company_name)
            company.ogrn = egrul.get("ogrn")
            company.egrul_status = egrul.get("status")
            company.okved_main = egrul.get("okved_main", {}).get("code")
            management = egrul.get("management", [])
            if management:
                company.director_name = management[0].get("full_name")

            reg_date_str = egrul.get("registration_date")
            if reg_date_str:
                try:
                    company.registration_date = datetime.strptime(reg_date_str, "%Y-%m-%d")
                except ValueError:
                    pass
            db.commit()

        save_check(db, app.id, "egrul", "SUCCESS", egrul)
        if "__error__" in egrul:
            return make_decision(db, app, "MANUAL_REVIEW", "Ошибка получения данных из ЕГРЮЛ.",
                                 reason_code="EGRUL_ERROR")

        zsk = await mocks_client.get_zsk(inn)
        save_check(db, app.id, "zsk", "SUCCESS", zsk)
        if "__error__" in zsk:
            return make_decision(db, app, "MANUAL_REVIEW", "Ошибка получения данных ЗСК.", reason_code="ZSK_ERROR")

        fns = await mocks_client.get_fns(inn)
        save_check(db, app.id, "fns", "SUCCESS", fns)
        if "__error__" in fns:
            return make_decision(db, app, "MANUAL_REVIEW", "Ошибка получения данных из ФНС.", reason_code="FNS_ERROR")

        risk = await mocks_client.get_risk_flags(inn)
        save_check(db, app.id, "risk", "SUCCESS", risk)
        if "__error__" in risk:
            return make_decision(db, app, "MANUAL_REVIEW", "Ошибка получения данных о судебных рисках.",
                                 reason_code="RISK_ERROR")

        if app.bki_consent_granted:
            bki = await mocks_client.get_bki(inn)
            save_check(db, app.id, "bki", "SUCCESS", bki)
            if "__error__" in bki:
                return make_decision(db, app, "MANUAL_REVIEW", "Ошибка получения кредитной истории (БКИ).",
                                     reason_code="BKI_ERROR")
        else:
            bki = {"__error__": "CONSENT_REQUIRED"}
            save_check(db, app.id, "bki", "FAILED", bki)

        update_status(db, app, "SCORING", "Валидация и скоринг")
        score, reject_reason = calculate_scoring(egrul, zsk, bki, fns, risk)

        logger.info(f"Заявка {app.id}: Итоговый балл = {score}")

        # --- МАТРИЦА РЕШЕНИЙ ---
        if reject_reason:
            make_decision(db, app, "REJECTED", reject_reason, reason_code="STOP_FACTOR", score=0)

        elif score >= 80:
            # A+ и A классы -> Одобрение (ставки 14% и 17.5%)
            terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)
            make_decision(db, app, "APPROVED",
                          f"Скоринг {score}/100. Грейд: {terms['tier']}",
                          amount=app.requested_amount, reason_code="APPROVED_BY_SCORING", score=score)

        elif score >= 60:
            # B и C классы -> Контроффер (ставки 21% и 23.5%, урезание суммы для C)
            terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)
            make_decision(db, app, "COUNTER_OFFER",
                          f"Скоринг {score}/100. Грейд: {terms['tier']}",
                          reason_code="REDUCED_AMOUNT", score=score)

        else:
            # D класс -> Отказ
            make_decision(db, app, "REJECTED", f"Отказ. Скоринг {score}/100. Высокий риск.", reason_code="LOW_SCORE",
                          score=0)

    except Exception as e:
        logger.error(f"Ошибка в конвейере: {str(e)}")
        db.rollback()
    finally:
        db.close()