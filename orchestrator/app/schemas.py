from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ==========================================
# 1. СХЕМЫ ДЛЯ КОМПАНИИ (Company)
# ==========================================
class CompanyBase(BaseModel):
    inn: str = Field(..., description="ИНН компании (10 или 12 цифр)")
    company_name: str = Field(..., description="Название компании")
    entity_type: str = Field(..., description="Тип: LEGAL_ENTITY или INDIVIDUAL_ENTREPRENEUR")


class CompanyResponse(CompanyBase):
    id: int
    egrul_status: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. СХЕМЫ ДЛЯ ЗАЯВКИ (Application)
# ==========================================
class LoanPurpose(str, Enum):
    EQUIPMENT = "EQUIPMENT"      # Покупка оборудования
    WORKING_CAPITAL = "WORKING_CAPITAL"  # Пополнение оборотных средств
    REAL_ESTATE = "REAL_ESTATE"  # Покупка недвижимости
    REFINANCING = "REFINANCING"  # Рефинансирование


class ApplicationCreate(BaseModel):
    client_inn: str = Field(..., description="ИНН клиента (10 или 12 цифр)")
    product_code: str = Field(..., description="Код продукта: CREDIT_LINE, OVERDRAFT, INVEST_CREDIT")
    requested_amount: float = Field(..., gt=0, description="Запрошенная сумма (должна быть > 0)")
    requested_term_months: int = Field(..., gt=0, le=120, description="Срок в месяцах (от 1 до 120)")
    purpose: LoanPurpose = Field(..., description="Цель кредита (выбор из списка)")
    bki_consent_granted: bool = Field(default=False, description="Согласие на запрос в БКИ")

    @field_validator("client_inn")
    @classmethod
    def validate_inn_checksum(cls, v: str) -> str:
        if len(v) not in [10, 12]:
            raise ValueError("ИНН должен содержать ровно 10 (для ЮЛ) или 12 (для ИП) цифр")
        if not v.isdigit():
            raise ValueError("ИНН должен состоять только из цифр")

        # Вспомогательная функция для расчета контрольной цифры
        def check_digit(inn_str, weights):
            return sum(int(digit) * weight for digit, weight in zip(inn_str, weights)) % 11 % 10

        if len(v) == 10:
            # Проверка для 10-значного ИНН (Юрлица)
            weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
            if check_digit(v, weights) != int(v[9]):
                raise ValueError("Неверная контрольная сумма ИНН (10 знаков)")
        else:
            # Проверка для 12-значного ИНН (ИП и физлица)
            weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            if check_digit(v, weights_11) != int(v[10]) or check_digit(v, weights_12) != int(v[11]):
                raise ValueError("Неверная контрольная сумма ИНН (12 знаков)")

        return v


class ApplicationResponse(BaseModel):
    id: int
    product_code: str
    requested_amount: float
    requested_term_months: int
    status: str
    current_step_name: Optional[str] = None
    created_at: datetime
    company: Optional[CompanyResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. СХЕМЫ ДЛЯ РЕЗУЛЬТАТОВ ПРОВЕРОК (CheckResult)
# ==========================================
class CheckResultResponse(BaseModel):
    id: int
    check_type: str
    execution_status: str
    raw_response: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. СХЕМЫ ДЛЯ РЕШЕНИЯ (Decision)
# ==========================================
class DecisionResponse(BaseModel):
    id: int
    decision_type: str
    approved_amount: Optional[float] = None
    approved_rate: Optional[float] = None
    reason_code: Optional[str] = None  # <--- ДОБАВИТЬ
    reason_text: Optional[str] = None
    decided_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. СХЕМЫ ДЛЯ АУДИТА (AuditEvent)
# ==========================================
class AuditEventResponse(BaseModel):
    id: int
    actor: str
    action: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. ДЕТАЛЬНЫЙ ОТВЕТ ПО ЗАЯВКЕ (Карточка заявки для банка)
# ==========================================
class ApplicationDetailResponse(ApplicationResponse):
    checks: List[CheckResultResponse] = []
    decision: Optional[DecisionResponse] = None
    audit_events: List[AuditEventResponse] = []

    model_config = ConfigDict(from_attributes=True)
