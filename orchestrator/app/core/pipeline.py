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
                  reason_code: str = "GENERAL", score: int = 0, details: list = None):
    """
    Принимает решение по заявке, рассчитывает условия и сохраняет всё в БД.
    """
    app.status = decision_type
    app.current_step_name = "Решение принято"

    # 1. Если отказ или ручная проверка — финансовые условия не рассчитываем
    if decision_type in ["REJECTED", "MANUAL_REVIEW"]:
        terms = {"rate": None, "penalty": None, "fee": None, "amount": None, "payment": None}
        product_info = ""
    else:
        # 2. Рассчитываем ставку, пени, комиссию и платеж на основе скоринга
        terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)

        # 3. Подбираем название продукта на основе цели кредита
        product_type_ru = "Универсальный кредит"
        if app.purpose == "EQUIPMENT":
            product_type_ru = "Целевой кредит на оборудование"
        elif app.purpose == "WORKING_CAPITAL":
            product_type_ru = "Овердрафт / Кредитная линия"
        elif app.purpose == "REAL_ESTATE":
            product_type_ru = "Инвестиционный кредит (недвижимость)"
        product_info = f" Рекомендуемый продукт: {product_type_ru}."

        # 4. Если это контроффер, сумма уже урезана внутри terms
        if decision_type == "COUNTER_OFFER":
            amount = terms["amount"]

    # 5. Создаем запись в БД
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
        scoring_details=details, # <--- СОХРАНЯЕМ РАСШИФРОВКУ
        decided_by="SYSTEM"
    )
    db.add(decision)

    # 6. Пишем событие в аудит
    audit = models.AuditEvent(
        application_id=app.id,
        actor="SYSTEM",
        action=f"DECISION_{decision_type}",
        old_status=app.status,
        new_status=decision_type,
        details={"reason_code": reason_code, "reason_text": reason, "score": score}
    )
    db.add(audit)

    # 7. Сохраняем всё в БД
    db.commit()
    logger.info(f"Заявка {app.id}: Решение {decision_type} (Скоринг: {score}, Грейд: {terms.get('tier', 'N/A')})")


def calculate_scoring(egrul, zsk, bki, fns, risk) -> tuple[int, str, list]:
    score = 0
    details = []

    def add_detail(category, points, max_points, reason):
        nonlocal score
        score += points
        details.append({
            "category": category,
            "score": points,
            "max_score": max_points,
            "reason": reason
        })

    # МГНОВЕННЫЙ ОТКАЗ (СТОП-ФАКТОРЫ)
    founders = egrul.get("founders", [])
    bankrupt_founders = risk.get("bankrupt_founders", [])
    for founder in founders:
        if founder.get("inn") in bankrupt_founders:
            return 0, "Стоп-фактор: Учредитель находится в стадии банкротства", [{"category": "Стоп-фактор", "score": 0, "max_score": 0, "reason": "Банкротство учредителя"}]

    if "__error__" in bki:
        return 0, "Стоп-фактор: Нет согласия на запрос кредитной истории (БКИ)", []
    if egrul.get("status") != "ACTIVE":
        return 0, "Стоп-фактор: Компания ликвидирована", []
    if fns.get("blocked_accounts"):
        return 0, "Стоп-фактор: Блокировка счетов", []
    if risk.get("verdict") == "HIGH_RISK":
        return 0, "Стоп-фактор: Критические судебные риски", []
    if bki.get("delinquency", {}).get("max_overdue_days", 0) > 90:
        return 0, "Стоп-фактор: Просрочки более 90 дней", []
    if egrul.get("has_unreliable_records") or egrul.get("management", [{}])[0].get("disqualified"):
        return 0, "Стоп-фактор: Недостоверные сведения / Дисквалификация", []

    # 1. СТАБИЛЬНОСТЬ БИЗНЕСА
    age = egrul.get("age_months", 0)
    if age > 24: add_detail("Стабильность бизнеса", 10, 10, "Компания старше 24 месяцев")
    elif 6 <= age <= 24: add_detail("Стабильность бизнеса", 5, 10, "Компания моложе 24 месяцев")
    else: add_detail("Стабильность бизнеса", 0, 10, "Компания моложе 6 месяцев")

    # 2. ФИНАНСОВОЕ ЗДОРОВЬЕ
    fin = fns.get("financials", {}).get("years", [{}])[0]
    profit = fin.get("net_profit", 0)
    is_growing = fin.get("is_growing", False)
    if profit > 0 and is_growing: add_detail("Финансовое здоровье", 25, 25, "Прибыль есть, выручка растет")
    elif profit > 0 and not is_growing: add_detail("Финансовое здоровье", 15, 25, "Прибыль есть, но нет роста")
    else: add_detail("Финансовое здоровье", 0, 25, "Убыток или нулевая отчетность")

    # 3. КРЕДИТНАЯ НАГРУЗКА
    revenue = fin.get("revenue", 1)
    monthly_revenue = revenue / 12
    monthly_payment = bki.get("total_monthly_payment", 0)
    dti = (monthly_payment / monthly_revenue) if monthly_revenue > 0 else 1.0
    if dti < 0.20: add_detail("Кредитная нагрузка", 25, 25, "Низкая нагрузка (менее 20% выручки)")
    elif 0.20 <= dti <= 0.40: add_detail("Кредитная нагрузка", 15, 25, "Средняя нагрузка (20-40% выручки)")
    else: add_detail("Кредитная нагрузка", 0, 25, "Высокая нагрузка (более 40% выручки)")

    # 4. НАЛОГОВАЯ ДИСЦИПЛИНА
    arrears_amount = fns.get("taxes", {}).get("arrears", {}).get("amount", 0)
    if arrears_amount == 0: add_detail("Налоговая дисциплина", 15, 15, "Нет задолженностей")
    elif arrears_amount < 10000: add_detail("Налоговая дисциплина", 5, 15, "Незначительная задолженность")
    else: add_detail("Налоговая дисциплина", 0, 15, "Крупная задолженность")

    # 5. СУДЕБНЫЕ РИСКИ
    cases = risk.get("sources", {}).get("arbitration_cases", {}).get("as_defendant", 0)
    if cases <= 2: add_detail("Судебные риски", 10, 10, "Минимальные судебные риски")
    elif 3 <= cases <= 5: add_detail("Судебные риски", 5, 10, "Умеренные судебные риски")
    else: add_detail("Судебные риски", 0, 10, "Высокое количество судов")

    # 6. НАДЕЖНОСТЬ БЕНЕФИЦИАРА
    director_score = bki.get("director_bki_score", 0)
    if director_score > 700: add_detail("Надежность бенефициара", 15, 15, "Отличный личный рейтинг")
    elif 600 <= director_score <= 700: add_detail("Надежность бенефициара", 5, 15, "Средний личный рейтинг")
    else: add_detail("Надежность бенефициара", 0, 15, "Низкий рейтинг или микрозаймы")

    return score, "", details


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

        # ИСПРАВЛЕНИЕ 1: Добавляем третью переменную details
        score, reject_reason, details = calculate_scoring(egrul, zsk, bki, fns, risk)

        logger.info(f"Заявка {app.id}: Итоговый балл = {score}")

        # --- МАТРИЦА РЕШЕНИЙ ---
        if reject_reason:
            # ИСПРАВЛЕНИЕ 2: Передаем details=details
            make_decision(db, app, "REJECTED", reject_reason, reason_code="STOP_FACTOR", score=0, details=details)

        elif score >= 80:
            terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)
            # ИСПРАВЛЕНИЕ 3: Передаем details=details
            make_decision(db, app, "APPROVED",
                          f"Скоринг {score}/100. Грейд: {terms['tier']}",
                          amount=app.requested_amount, reason_code="APPROVED_BY_SCORING", score=score, details=details)

        elif score >= 60:
            terms = calculate_loan_terms(score, app.requested_amount, app.requested_term_months)
            # ИСПРАВЛЕНИЕ 4: Передаем details=details
            make_decision(db, app, "COUNTER_OFFER",
                          f"Скоринг {score}/100. Грейд: {terms['tier']}",
                          reason_code="REDUCED_AMOUNT", score=score, details=details)

        else:
            # ИСПРАВЛЕНИЕ 5: Передаем details=details
            make_decision(db, app, "REJECTED", f"Отказ. Скоринг {score}/100. Высокий риск.", reason_code="LOW_SCORE",
                          score=0, details=details)

    except Exception as e:
        logger.error(f"Ошибка в конвейере: {str(e)}")
        db.rollback()
    finally:
        db.close()