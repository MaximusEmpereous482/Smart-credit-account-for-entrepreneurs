from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean, Index, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    inn = Column(String(12), unique=True, index=True, nullable=False)
    ogrn = Column(String(15), unique=True, nullable=True)
    company_name = Column(String(255), nullable=False)
    entity_type = Column(String(20), nullable=False)
    registration_date = Column(DateTime, nullable=True)
    director_name = Column(String(255), nullable=True)
    okved_main = Column(String(10), nullable=True)
    egrul_status = Column(String(50), nullable=True)

    applications = relationship("Application", back_populates="company", cascade="all, delete-orphan")
    __table_args__ = (Index('idx_company_inn_name', 'inn', 'company_name'),)


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    product_code = Column(String(50), nullable=False)
    requested_amount = Column(Float, nullable=False)
    requested_term_months = Column(Integer, nullable=False)
    purpose = Column(String(50), nullable=False)
    status = Column(String(50), default="DRAFT", nullable=False)
    current_step_name = Column(String(100), nullable=True)
    bki_consent_granted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    company = relationship("Company", back_populates="applications")
    checks = relationship("CheckResult", back_populates="application", cascade="all, delete-orphan")
    decision = relationship("Decision", back_populates="application", uselist=False, cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="application", cascade="all, delete-orphan")

    __table_args__ = (Index('idx_application_status', 'status'), Index('idx_application_created', 'created_at'),)


class CheckResult(Base):
    __tablename__ = "check_results"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    check_type = Column(String(50), nullable=False)
    execution_status = Column(String(20), nullable=False)  # SUCCESS, FAILED
    error_message = Column(String(255), nullable=True)  # <--- ДОБАВИЛИ: Человекочитаемая причина
    raw_response = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    application = relationship("Application", back_populates="checks")


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), unique=True, nullable=False)
    decision_type = Column(String(50), nullable=False)
    approved_amount = Column(Float, nullable=True)
    approved_term_months = Column(Integer, nullable=True)
    approved_rate = Column(Float, nullable=True)
    penalty_rate = Column(Float, nullable=True)            # Пени (% в день)
    issuance_fee_percent = Column(Float, nullable=True)    # Комиссия за выдачу (%)
    monthly_payment = Column(Float, nullable=True)         # Ежемесячный платеж
    reason_code = Column(String(50), nullable=True)
    reason_text = Column(Text, nullable=True)
    decided_by = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    application = relationship("Application", back_populates="decision")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    actor = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    application = relationship("Application", back_populates="audit_events")
