from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    unit_name: str
    assigned_station_code: Optional[str] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class AnomalyStatusUpdate(BaseModel):
    status: str = Field(..., description="Open | In Progress | Resolved | Verified")
    resolution_notes: str = Field(..., min_length=3)


class EscalationRequest(BaseModel):
    reason: Optional[str] = "Batas waktu SLA penanganan telah terlewati (Simulasi Eskalasi)."


class DataDictionaryCreate(BaseModel):
    parameter_code: str
    display_name: str
    standard_unit: str
    accepted_aliases: str
    valid_min: float
    valid_max: float
    physical_min: float
    physical_max: float
    max_step_per_hour: float
    persistence_limit: int = 4
    wmo_reference: str
    description: str


class DataDictionaryUpdate(BaseModel):
    display_name: Optional[str] = None
    standard_unit: Optional[str] = None
    accepted_aliases: Optional[str] = None
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    physical_min: Optional[float] = None
    physical_max: Optional[float] = None
    max_step_per_hour: Optional[float] = None
    persistence_limit: Optional[int] = None
    wmo_reference: Optional[str] = None
    description: Optional[str] = None


class RaciUpdate(BaseModel):
    responsible_role: Optional[str] = None
    accountable_role: Optional[str] = None
    consulted_role: Optional[str] = None
    informed_role: Optional[str] = None
    assigned_pic_username: Optional[str] = None
    assigned_pic_name: Optional[str] = None
    sla_hours_critical: Optional[int] = None
    sla_hours_warning: Optional[int] = None


class EtlBatchSummary(BaseModel):
    batch_code: str
    filename: str
    uploaded_at: datetime
    total_rows: int
    valid_count: int
    warning_count: int
    critical_count: int
    new_anomaly_cases: int
    stations_detected: List[str]
