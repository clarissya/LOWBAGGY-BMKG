from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(String(32), nullable=False)  # staf_qc | teknisi | forecaster | manajemen
    unit_name = Column(String(120), nullable=False)
    assigned_station_code = Column(String(32), nullable=True)


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    station_code = Column(String(32), unique=True, nullable=False, index=True)
    station_name = Column(String(128), nullable=False)
    region = Column(String(128), nullable=False)
    station_type = Column(String(64), nullable=False, default="AWS Maritim")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)


class DataDictionary(Base):
    __tablename__ = "data_dictionary"

    id = Column(Integer, primary_key=True, index=True)
    parameter_code = Column(String(40), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    standard_unit = Column(String(32), nullable=False)
    accepted_aliases = Column(Text, nullable=False)
    valid_min = Column(Float, nullable=False)
    valid_max = Column(Float, nullable=False)
    physical_min = Column(Float, nullable=False)
    physical_max = Column(Float, nullable=False)
    max_step_per_hour = Column(Float, nullable=False)
    persistence_limit = Column(Integer, nullable=False, default=4)
    wmo_reference = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)


class RaciRegistry(Base):
    __tablename__ = "raci_registry"

    id = Column(Integer, primary_key=True, index=True)
    station_code = Column(String(32), nullable=False, index=True)
    station_name = Column(String(128), nullable=False)
    parameter_scope = Column(String(64), nullable=False, default="ALL")
    responsible_role = Column(String(128), nullable=False)  # R: Observer / Teknisi AWS
    accountable_role = Column(String(128), nullable=False)  # A: Kepala UPT / Datin
    consulted_role = Column(String(128), nullable=False)    # C: Datin (QC) / Forecaster
    informed_role = Column(String(128), nullable=False)     # I: Forecaster & Manajemen
    assigned_pic_username = Column(String(64), nullable=False)
    assigned_pic_name = Column(String(120), nullable=False)
    sla_hours_critical = Column(Integer, nullable=False, default=4)
    sla_hours_warning = Column(Integer, nullable=False, default=24)


class SopGuide(Base):
    __tablename__ = "sop_guides"

    id = Column(Integer, primary_key=True, index=True)
    sop_code = Column(String(32), unique=True, nullable=False, index=True)
    violation_type = Column(String(64), nullable=False, index=True)
    parameter_scope = Column(String(64), nullable=False, default="ALL")
    title = Column(String(180), nullable=False)
    steps_text = Column(Text, nullable=False)
    sla_target_hours = Column(Integer, nullable=False, default=12)
    escalation_target = Column(String(120), nullable=False)


class EtlBatch(Base):
    __tablename__ = "etl_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_code = Column(String(48), unique=True, nullable=False, index=True)
    filename = Column(String(200), nullable=False)
    uploaded_by = Column(String(64), nullable=False)
    uploaded_at = Column(DateTime, default=utcnow, nullable=False)
    interval_type = Column(String(16), nullable=False, default="1h")  # 10m | 1h
    total_rows = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    critical_count = Column(Integer, nullable=False, default=0)
    stations_detected = Column(Text, nullable=False, default="")


class ObservationRecord(Base):
    __tablename__ = "observation_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("etl_batches.id"), nullable=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    interval_type = Column(String(16), nullable=False, default="1h")  # 10m (UPT) | 1h (Pusat)
    station_code = Column(String(32), nullable=False, index=True)
    station_name = Column(String(128), nullable=False)
    parameter_code = Column(String(40), nullable=False, index=True)
    parameter_name = Column(String(100), nullable=False)
    raw_value = Column(String(64), nullable=True)
    numeric_value = Column(Float, nullable=True)
    unit = Column(String(32), nullable=False)
    qc_status = Column(String(32), nullable=False, index=True)  # Valid | Warning/Suspect | Critical/Missing
    qc_rule_triggered = Column(String(64), nullable=True)
    qc_detail = Column(Text, nullable=True)
    schema_valid = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    anomaly_case = relationship("AnomalyCase", back_populates="observation", uselist=False)


class AnomalyCase(Base):
    __tablename__ = "anomaly_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_code = Column(String(48), unique=True, nullable=False, index=True)
    observation_id = Column(Integer, ForeignKey("observation_records.id"), nullable=False, unique=True)
    station_code = Column(String(32), nullable=False, index=True)
    station_name = Column(String(128), nullable=False)
    parameter_code = Column(String(40), nullable=False, index=True)
    parameter_name = Column(String(100), nullable=False)
    observed_at = Column(DateTime, nullable=False, index=True)
    raw_value = Column(String(64), nullable=True)
    severity = Column(String(32), nullable=False, index=True)
    violation_type = Column(String(64), nullable=False)
    diagnostic_message = Column(Text, nullable=False)

    data_owner = Column(String(128), nullable=False)
    data_steward = Column(String(128), nullable=False)
    responsible_unit = Column(String(128), nullable=False)
    assigned_pic_username = Column(String(64), nullable=False, index=True)
    assigned_pic_name = Column(String(120), nullable=False)
    sop_code = Column(String(32), nullable=False)

    status = Column(String(32), nullable=False, default="Open", index=True)  # Open | In Progress | Resolved | Verified
    resolution_notes = Column(Text, nullable=True)
    sla_due_at = Column(DateTime, nullable=False)
    is_escalated = Column(Boolean, nullable=False, default=False)
    escalated_at = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    observation = relationship("ObservationRecord", back_populates="anomaly_case")


class AuditTrail(Base):
    """Append-only immutable audit log."""

    __tablename__ = "audit_trail"

    id = Column(Integer, primary_key=True, index=True)
    audit_code = Column(String(48), unique=True, nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("anomaly_cases.id"), nullable=True, index=True)
    case_code = Column(String(48), nullable=True, index=True)
    event_time = Column(DateTime, default=utcnow, nullable=False, index=True)
    actor_username = Column(String(64), nullable=False)
    actor_name = Column(String(120), nullable=False)
    actor_role = Column(String(32), nullable=False)
    action_type = Column(String(48), nullable=False, index=True)
    previous_status = Column(String(32), nullable=True)
    new_status = Column(String(32), nullable=True)
    assigned_pic = Column(String(120), nullable=True)
    notes = Column(Text, nullable=False)
