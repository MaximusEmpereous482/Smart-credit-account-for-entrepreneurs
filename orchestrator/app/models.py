from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    inn = Column(String, unique=True, index=True)
    ogrn = Column(String, unique=True)
    company_name = Column(String)
    entity_type = Column(String)
    registration_date = Column(DateTime)
    director_name = Column(String)
    okved_main = Column(String)
    egrul_status = Column(String)

    applications = relationship("Application", back_populates="company")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))

    product_code = Column(String)
    requested_amount = Column(Float)
    requested_term_months = Column(Integer)
    purpose = Column(String)

    status = Column(String, default="DRAFT")
    current_step_name = Column(String)

    bki_consent_granted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи (здесь важно точное написание имен классов)
    company = relationship("Company", back_populates="applications")
    checks = relationship("CheckResult", back_populates="application")
    decision = relationship("Decision", back_populates="application", uselist=False)
    audit_events = relationship("AuditEvent", back_populates="application")


class CheckResult(Base):
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))

    check_type = Column(String)
    execution_status = Column(String)

    score_value = Column(Integer, nullable=True)
    max_overdue_days = Column(Integer, nullable=True)
    risk_zone = Column(String, nullable=True)
    debt_load_dti = Column(Float, nullable=True)

    raw_response = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="checks")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), unique=True)

    decision_type = Column(String)
    approved_amount = Column(Float, nullable=True)
    approved_term_months = Column(Integer, nullable=True)
    approved_rate = Column(Float, nullable=True)
    reason_code = Column(String)
    reason_text = Column(String)
    decided_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="decision")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))

    actor = Column(String)
    action = Column(String)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="audit_events")