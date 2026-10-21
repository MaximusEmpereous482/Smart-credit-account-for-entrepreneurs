from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


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
class ApplicationCreate(BaseModel):
    client_inn: str = Field(..., description="ИНН клиента (для поиска в ЕГРЮЛ)")
    product_code: str = Field(..., description="Код продукта: CREDIT_LINE, OVERDRAFT, INVEST_CREDIT")
    requested_amount: float = Field(..., gt=0, description="Запрошенная сумма (должна быть > 0)")
    requested_term_months: int = Field(..., gt=0, le=120, description="Срок в месяцах (от 1 до 120)")
    purpose: str = Field(..., description="Цель кредита")
    bki_consent_granted: bool = Field(default=False, description="Согласие на запрос в БКИ")


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