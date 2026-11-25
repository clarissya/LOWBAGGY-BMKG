from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, require_roles, verify_password
from app.config import APP_TITLE, BASE_DIR
from app.database import Base, SessionLocal, engine, get_db
from app.etl_qc import process_etl_upload
from app.models import (
    AnomalyCase,
    AuditTrail,
    DataDictionary,
    EtlBatch,
    ObservationRecord,
    RaciRegistry,
    SopGuide,
    Station,
    User,
)
from app.schemas import (
    AnomalyStatusUpdate,
    DataDictionaryCreate,
    DataDictionaryUpdate,
    EscalationRequest,
    LoginRequest,
    LoginResponse,
    RaciUpdate,
    ReturnToDatinRequest,
    UserOut,
)
from app.seed import seed_baseline_observations, seed_reference_data

STATIC_DIR = BASE_DIR / "static"
SAMPLE_DIR = BASE_DIR / "sample_data"


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_reference_data(db)
        seed_baseline_observations(db)
    finally:
        db.close()
    yield


app = FastAPI(title=APP_TITLE, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "app": APP_TITLE}


# ==================== AUTH & RBAC ====================

@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah")
    token = create_token(user)
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assigned_open = (
        db.query(AnomalyCase)
        .filter(
            AnomalyCase.assigned_pic_username == current_user.username,
            AnomalyCase.status.in_(["Open", "In Progress"]),
        )
        .count()
    )
    total_open = (
        db.query(AnomalyCase)
        .filter(AnomalyCase.status.in_(["Open", "In Progress"]))
        .count()
    )
    return {
        "user": UserOut.model_validate(current_user),
        "notifications": {
            "assigned_open_cases": assigned_open,
            "total_open_cases": total_open,
        },
    }


@app.get("/api/meta/filters")
def get_filter_metadata(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stations = db.query(Station).order_by(Station.station_code).all()
    params = db.query(DataDictionary).order_by(DataDictionary.parameter_code).all()
    return {
        "stations": [{"station_code": s.station_code, "station_name": s.station_name, "region": s.region} for s in stations],
        "parameters": [{"parameter_code": p.parameter_code, "display_name": p.display_name, "standard_unit": p.standard_unit} for p in params],
    }


# ==================== PAGE 1: DASHBOARD & TENDENCY CHART ====================

@app.get("/api/dashboard")
def get_dashboard(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    station_code: Optional[str] = Query(default=None),
    parameter_code: Optional[str] = Query(default=None),
    interval_type: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    obs_q = db.query(ObservationRecord)
    case_q = db.query(AnomalyCase)

    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            obs_q = obs_q.filter(ObservationRecord.observed_at >= dt_start)
            case_q = case_q.filter(AnomalyCase.observed_at >= dt_start)
        except ValueError:
            pass
    if end_date:
        try:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            obs_q = obs_q.filter(ObservationRecord.observed_at <= dt_end)
            case_q = case_q.filter(AnomalyCase.observed_at <= dt_end)
        except ValueError:
            pass
    if station_code and station_code != "ALL":
        obs_q = obs_q.filter(ObservationRecord.station_code == station_code)
        case_q = case_q.filter(AnomalyCase.station_code == station_code)
    if parameter_code and parameter_code != "ALL":
        obs_q = obs_q.filter(ObservationRecord.parameter_code == parameter_code)
        case_q = case_q.filter(AnomalyCase.parameter_code == parameter_code)
    if interval_type and interval_type != "ALL":
        obs_q = obs_q.filter(ObservationRecord.interval_type == interval_type)

    observations = obs_q.all()
    cases = case_q.all()
    now = utcnow()

    total_obs = len(observations)
    if total_obs > 0:
        non_missing = sum(1 for o in observations if o.qc_rule_triggered != "Missing Data" and o.numeric_value is not None)
        schema_valid_count = sum(1 for o in observations if o.schema_valid)
        valid_qc_count = sum(1 for o in observations if o.qc_status == "Valid")
        completeness_pct = round((non_missing / total_obs) * 100, 1)
        validity_pct = round((schema_valid_count / total_obs) * 100, 1)
        valid_qc_pct = round((valid_qc_count / total_obs) * 100, 1)
    else:
        completeness_pct = 0.0
        validity_pct = 0.0
        valid_qc_pct = 0.0

    total_anomalies = sum(1 for o in observations if o.qc_status != "Valid")
    unhandled_cases = sum(1 for c in cases if c.status in ("Open", "In Progress"))
    resolved_cases = sum(1 for c in cases if c.status in ("Resolved", "Verified"))
    escalated_cases = sum(1 for c in cases if c.is_escalated or (c.status in ("Open", "In Progress") and c.sla_due_at < now))

    if len(cases) > 0:
        compliant = sum(
            1
            for c in cases
            if not c.is_escalated and (
                (c.status in ("Resolved", "Verified") and (c.resolved_at is None or c.resolved_at <= c.sla_due_at))
                or (c.status in ("Open", "In Progress") and c.sla_due_at >= now)
            )
        )
        sop_compliance_pct = round((compliant / len(cases)) * 100, 1)
    else:
        sop_compliance_pct = 100.0

    station_agg = {}
    for o in observations:
        st = station_agg.setdefault(
            o.station_code,
            {
                "station_code": o.station_code,
                "station_name": o.station_name,
                "total": 0,
                "valid": 0,
                "warning": 0,
                "critical": 0,
                "non_missing": 0,
                "open_cases": 0,
                "resolved_cases": 0,
                "escalated_cases": 0,
            },
        )
        st["total"] += 1
        if o.qc_rule_triggered != "Missing Data" and o.numeric_value is not None:
            st["non_missing"] += 1
        if o.qc_status == "Valid":
            st["valid"] += 1
        elif o.qc_status == "Warning/Suspect":
            st["warning"] += 1
        else:
            st["critical"] += 1

    for c in cases:
        st = station_agg.get(c.station_code)
        if st:
            if c.status in ("Open", "In Progress"):
                st["open_cases"] += 1
            else:
                st["resolved_cases"] += 1
            if c.is_escalated or (c.status in ("Open", "In Progress") and c.sla_due_at < now):
                st["escalated_cases"] += 1

    by_station = []
    for st in sorted(station_agg.values(), key=lambda x: x["warning"] + x["critical"], reverse=True):
        st["completeness_pct"] = round((st["non_missing"] / st["total"]) * 100, 1) if st["total"] else 0.0
        by_station.append(st)

    param_agg = {}
    for o in observations:
        pm = param_agg.setdefault(
            o.parameter_code,
            {
                "parameter_code": o.parameter_code,
                "parameter_name": o.parameter_name,
                "total": 0,
                "valid": 0,
                "warning": 0,
                "critical": 0,
                "non_missing": 0,
            },
        )
        pm["total"] += 1
        if o.qc_rule_triggered != "Missing Data" and o.numeric_value is not None:
            pm["non_missing"] += 1
        if o.qc_status == "Valid":
            pm["valid"] += 1
        elif o.qc_status == "Warning/Suspect":
            pm["warning"] += 1
        else:
            pm["critical"] += 1

    by_parameter = []
    for pm in sorted(param_agg.values(), key=lambda x: x["warning"] + x["critical"], reverse=True):
        pm["completeness_pct"] = round((pm["non_missing"] / pm["total"]) * 100, 1) if pm["total"] else 0.0
        by_parameter.append(pm)

    violation_counts = {}
    for o in observations:
        if o.qc_status != "Valid":
            v = o.qc_rule_triggered or "Lainnya"
            violation_counts[v] = violation_counts.get(v, 0) + 1

    by_violation = [{"violation_type": k, "count": v} for k, v in sorted(violation_counts.items(), key=lambda kv: kv[1], reverse=True)]

    return {
        "kpis": {
            "total_observations": total_obs,
            "completeness_pct": completeness_pct,
            "validity_pct": validity_pct,
            "valid_qc_pct": valid_qc_pct,
            "total_anomalies": total_anomalies,
            "unhandled_cases": unhandled_cases,
            "resolved_cases": resolved_cases,
            "escalated_cases": escalated_cases,
            "sop_compliance_pct": sop_compliance_pct,
        },
        "by_station": by_station,
        "by_parameter": by_parameter,
        "by_violation": by_violation,
    }


@app.get("/api/dashboard/timeseries")
def get_dashboard_timeseries(
    station_code: str = Query(default="AWS-TPRK"),
    parameter_code: str = Query(default="temperature"),
    window_hours: int = Query(default=24),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return 24-hour or 72-hour (3-day) tendency series with QC flags for Forecaster & Datin."""
    q = db.query(ObservationRecord).filter(
        ObservationRecord.station_code == station_code,
        ObservationRecord.parameter_code == parameter_code,
    )
    latest = q.order_by(ObservationRecord.observed_at.desc()).first()
    if not latest:
        return {"station_code": station_code, "parameter_code": parameter_code, "unit": "", "points": []}

    cutoff = latest.observed_at - timedelta(hours=window_hours)
    rows = (
        q.filter(ObservationRecord.observed_at >= cutoff)
        .order_by(ObservationRecord.observed_at.asc())
        .all()
    )
    return {
        "station_code": station_code,
        "station_name": latest.station_name,
        "parameter_code": parameter_code,
        "parameter_name": latest.parameter_name,
        "unit": latest.unit,
        "window_hours": window_hours,
        "points": [
            {
                "id": r.id,
                "observed_at": r.observed_at.isoformat(),
                "interval_type": r.interval_type,
                "raw_value": r.raw_value,
                "numeric_value": r.numeric_value,
                "qc_status": r.qc_status,
                "qc_rule_triggered": r.qc_rule_triggered,
                "qc_detail": r.qc_detail,
            }
            for r in rows
        ],
    }


# ==================== PAGE 2: ETL & AUTO QC ====================

@app.post("/api/etl/upload")
async def upload_etl_files(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="Pilih minimal satu file CSV atau Excel.")

    results = []
    for f in files:
        content = await f.read()
        try:
            summary = process_etl_upload(db, content, f.filename or "upload.csv", current_user)
            results.append(summary)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Gagal memproses '{f.filename}': {exc}") from exc

    return {
        "message": f"{len(results)} file berhasil diproses melalui mesin ETL & QC WMO-No. 8.",
        "batches": results,
    }


@app.post("/api/etl/import-samples")
def import_sample_files(
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    sample_files = sorted(SAMPLE_DIR.glob("*.csv"))
    if not sample_files:
        raise HTTPException(status_code=404, detail="File sampel CSV tidak ditemukan di folder sample_data.")

    results = []
    for path in sample_files:
        summary = process_etl_upload(db, path.read_bytes(), path.name, current_user)
        results.append(summary)

    return {
        "message": f"{len(results)} file sampel AWS Maritim berhasil distandarkan & divalidasi otomatis.",
        "batches": results,
    }


@app.post("/api/etl/reset-demo")
def reset_demo_data(
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    db.query(AuditTrail).delete()
    db.query(AnomalyCase).delete()
    db.query(ObservationRecord).delete()
    db.query(EtlBatch).delete()
    db.commit()
    seed_baseline_observations(db)
    return {"message": "Data observasi & kasus anomali telah direset ke baseline 24 jam awal."}


@app.get("/api/etl/batches")
def list_etl_batches(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    batches = db.query(EtlBatch).order_by(EtlBatch.uploaded_at.desc()).limit(30).all()
    return [
        {
            "batch_code": b.batch_code,
            "filename": b.filename,
            "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at.isoformat(),
            "interval_type": b.interval_type,
            "total_rows": b.total_rows,
            "valid_count": b.valid_count,
            "warning_count": b.warning_count,
            "critical_count": b.critical_count,
            "stations_detected": b.stations_detected,
        }
        for b in batches
    ]


@app.get("/api/samples/list")
def list_sample_files(current_user: User = Depends(get_current_user)):
    files = sorted(SAMPLE_DIR.glob("*.csv")) + sorted(SAMPLE_DIR.glob("*.xlsx"))
    return [{"filename": f.name, "size_bytes": f.stat().st_size} for f in files]


@app.get("/api/samples/download/{filename}")
def download_sample_file(filename: str):
    target = (SAMPLE_DIR / Path(filename).name).resolve()
    if not target.exists() or target.parent != SAMPLE_DIR.resolve():
        raise HTTPException(status_code=404, detail="File sampel tidak ditemukan.")
    return FileResponse(path=target, filename=target.name)


# ==================== PAGE 3: ANOMALY MONITORING & FOLLOW-UP ====================

def _serialize_case(case: AnomalyCase, now: datetime) -> dict:
    overdue = case.status in ("Open", "In Progress") and case.sla_due_at < now
    return {
        "id": case.id,
        "case_code": case.case_code,
        "station_code": case.station_code,
        "station_name": case.station_name,
        "parameter_code": case.parameter_code,
        "parameter_name": case.parameter_name,
        "observed_at": case.observed_at.isoformat(),
        "raw_value": case.raw_value,
        "severity": case.severity,
        "violation_type": case.violation_type,
        "diagnostic_message": case.diagnostic_message,
        "data_owner": case.data_owner,
        "data_steward": case.data_steward,
        "responsible_unit": case.responsible_unit,
        "assigned_pic_username": case.assigned_pic_username,
        "assigned_pic_name": case.assigned_pic_name,
        "sop_code": case.sop_code,
        "status": case.status,
        "resolution_notes": case.resolution_notes,
        "sla_due_at": case.sla_due_at.isoformat(),
        "is_escalated": case.is_escalated,
        "is_overdue": overdue,
        "escalated_at": case.escalated_at.isoformat() if case.escalated_at else None,
        "detected_at": case.detected_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
    }


@app.get("/api/anomalies")
def list_anomalies(
    station_code: Optional[str] = Query(default=None),
    parameter_code: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    assigned_to_me: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(AnomalyCase)
    if station_code and station_code != "ALL":
        q = q.filter(AnomalyCase.station_code == station_code)
    if parameter_code and parameter_code != "ALL":
        q = q.filter(AnomalyCase.parameter_code == parameter_code)
    if severity and severity != "ALL":
        q = q.filter(AnomalyCase.severity == severity)
    if status_filter and status_filter != "ALL":
        q = q.filter(AnomalyCase.status == status_filter)
    if assigned_to_me:
        q = q.filter(AnomalyCase.assigned_pic_username == current_user.username)
    if search:
        pattern = f"%{search.strip()}%"
        q = q.filter(
            (AnomalyCase.case_code.ilike(pattern))
            | (AnomalyCase.station_name.ilike(pattern))
            | (AnomalyCase.parameter_name.ilike(pattern))
            | (AnomalyCase.violation_type.ilike(pattern))
            | (AnomalyCase.assigned_pic_name.ilike(pattern))
        )

    cases = q.order_by(AnomalyCase.detected_at.desc(), AnomalyCase.id.desc()).all()
    now = utcnow()
    return [_serialize_case(c, now) for c in cases]


@app.get("/api/anomalies/{case_id}")
def get_anomaly_detail(
    case_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(AnomalyCase).filter(AnomalyCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Kasus anomali tidak ditemukan.")

    raci = db.query(RaciRegistry).filter(RaciRegistry.station_code == case.station_code).first()
    sop = db.query(SopGuide).filter(SopGuide.sop_code == case.sop_code).first()
    obs = db.query(ObservationRecord).filter(ObservationRecord.id == case.observation_id).first()
    logs = (
        db.query(AuditTrail)
        .filter(AuditTrail.case_id == case.id)
        .order_by(AuditTrail.event_time.desc(), AuditTrail.id.desc())
        .all()
    )

    # Fetch nearby +/- 12h tendency context for Pak Fajar / Datin review
    nearby = (
        db.query(ObservationRecord)
        .filter(
            ObservationRecord.station_code == case.station_code,
            ObservationRecord.parameter_code == case.parameter_code,
            ObservationRecord.observed_at >= case.observed_at - timedelta(hours=12),
            ObservationRecord.observed_at <= case.observed_at + timedelta(hours=6),
        )
        .order_by(ObservationRecord.observed_at.asc())
        .limit(18)
        .all()
    )

    now = utcnow()
    data = _serialize_case(case, now)
    data["unit"] = obs.unit if obs else ""
    data["interval_type"] = obs.interval_type if obs else "1h"
    data["numeric_value"] = obs.numeric_value if obs else None
    data["raci"] = {
        "responsible": raci.responsible_role if raci else case.responsible_unit,
        "accountable": raci.accountable_role if raci else case.data_owner,
        "consulted": raci.consulted_role if raci else case.data_steward,
        "informed": raci.informed_role if raci else "Forecaster & Manajemen",
        "assigned_pic_name": case.assigned_pic_name,
        "assigned_pic_username": case.assigned_pic_username,
    }
    data["sop"] = {
        "sop_code": sop.sop_code if sop else case.sop_code,
        "title": sop.title if sop else "Rancangan SOP Penanganan Anomali Observasi",
        "steps": sop.steps_text.split("\n") if sop else ["1. Periksa kondisi sensor dan logger di lapangan."],
        "sla_target_hours": sop.sla_target_hours if sop else 12,
        "escalation_target": sop.escalation_target if sop else "Koordinator Datin & Kepala UPT",
    }
    data["nearby_timeseries"] = [
        {
            "observed_at": n.observed_at.isoformat(),
            "raw_value": n.raw_value,
            "numeric_value": n.numeric_value,
            "qc_status": n.qc_status,
            "is_current": n.id == case.observation_id,
        }
        for n in nearby
    ]
    data["history"] = [
        {
            "audit_code": l.audit_code,
            "event_time": l.event_time.isoformat(),
            "actor_name": l.actor_name,
            "actor_role": l.actor_role,
            "action_type": l.action_type,
            "previous_status": l.previous_status,
            "new_status": l.new_status,
            "notes": l.notes,
        }
        for l in logs
    ]
    return data


@app.patch("/api/anomalies/{case_id}/status")
def update_anomaly_status(
    case_id: int,
    payload: AnomalyStatusUpdate,
    current_user: User = Depends(require_roles("teknisi", "staf_qc")),
    db: Session = Depends(get_db),
):
    case = db.query(AnomalyCase).filter(AnomalyCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Kasus anomali tidak ditemukan.")

    allowed_statuses = {"Open", "In Progress", "Resolved", "Verified"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Status tidak valid. Pilih: {', '.join(sorted(allowed_statuses))}")

    if current_user.role == "teknisi" and payload.status == "Verified":
        raise HTTPException(status_code=403, detail="Hanya Bidang Datin (Staf QC) yang dapat memverifikasi penyelesaian kasus.")

    now = utcnow()
    prev_status = case.status
    case.status = payload.status
    case.resolution_notes = payload.resolution_notes.strip()
    case.updated_at = now
    if payload.status in ("Resolved", "Verified") and case.resolved_at is None:
        case.resolved_at = now

    action_type = "VERIFIED" if payload.status == "Verified" else "STATUS_CHANGE"
    db.add(
        AuditTrail(
            audit_code=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            case_id=case.id,
            case_code=case.case_code,
            event_time=now,
            actor_username=current_user.username,
            actor_name=current_user.full_name,
            actor_role=current_user.role,
            action_type=action_type,
            previous_status=prev_status,
            new_status=payload.status,
            assigned_pic=case.assigned_pic_name,
            notes=payload.resolution_notes.strip(),
        )
    )
    db.commit()
    return _serialize_case(case, now)


@app.post("/api/anomalies/{case_id}/return-to-datin")
def return_case_to_datin(
    case_id: int,
    payload: ReturnToDatinRequest,
    current_user: User = Depends(require_roles("forecaster", "staf_qc")),
    db: Session = Depends(get_db),
):
    """Alur nyata dari wawancara BMKG: Forecaster mengembalikan data suspect/salah ke Bidang Datin untuk dikoreksi."""
    case = db.query(AnomalyCase).filter(AnomalyCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Kasus anomali tidak ditemukan.")

    now = utcnow()
    prev_status = case.status
    case.status = "Open"
    case.resolved_at = None
    case.resolution_notes = f"[Dikembalikan Forecaster] {payload.notes.strip()}"
    case.updated_at = now

    db.add(
        AuditTrail(
            audit_code=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            case_id=case.id,
            case_code=case.case_code,
            event_time=now,
            actor_username=current_user.username,
            actor_name=current_user.full_name,
            actor_role=current_user.role,
            action_type="RETURNED_TO_DATIN",
            previous_status=prev_status,
            new_status="Open",
            assigned_pic="Bidang Datin (QC) & Observer",
            notes=f"Temuan Forecaster dikembalikan ke Datin: {payload.notes.strip()}",
        )
    )
    db.commit()
    return _serialize_case(case, now)


@app.post("/api/anomalies/{case_id}/escalate")
def escalate_anomaly_case(
    case_id: int,
    payload: EscalationRequest,
    current_user: User = Depends(require_roles("staf_qc", "teknisi")),
    db: Session = Depends(get_db),
):
    case = db.query(AnomalyCase).filter(AnomalyCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Kasus anomali tidak ditemukan.")
    if case.status in ("Resolved", "Verified"):
        raise HTTPException(status_code=400, detail="Kasus yang sudah selesai tidak dapat dieskalasi.")

    now = utcnow()
    case.is_escalated = True
    case.escalated_at = now
    case.updated_at = now
    if case.sla_due_at > now:
        case.sla_due_at = now

    reason_text = payload.reason.strip() if payload.reason else "Batas waktu SLA penanganan telah terlewati."
    db.add(
        AuditTrail(
            audit_code=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            case_id=case.id,
            case_code=case.case_code,
            event_time=now,
            actor_username=current_user.username,
            actor_name=current_user.full_name,
            actor_role=current_user.role,
            action_type="ESCALATED",
            previous_status=case.status,
            new_status=case.status,
            assigned_pic=case.data_owner,
            notes=f"ESKALASI KE {case.data_owner} & Manajemen: {reason_text}",
        )
    )
    db.commit()
    return _serialize_case(case, now)


# ==================== PAGE 4: GOVERNANCE & AUDIT TRAIL ====================

@app.get("/api/governance/audit-trail")
def get_audit_trail(
    case_code: Optional[str] = Query(default=None),
    action_type: Optional[str] = Query(default=None),
    limit: int = Query(default=150, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(AuditTrail)
    if case_code:
        q = q.filter(AuditTrail.case_code.ilike(f"%{case_code.strip()}%"))
    if action_type and action_type != "ALL":
        q = q.filter(AuditTrail.action_type == action_type)

    rows = q.order_by(AuditTrail.event_time.desc(), AuditTrail.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "audit_code": r.audit_code,
            "case_id": r.case_id,
            "case_code": r.case_code or "-",
            "event_time": r.event_time.isoformat(),
            "actor_username": r.actor_username,
            "actor_name": r.actor_name,
            "actor_role": r.actor_role,
            "action_type": r.action_type,
            "previous_status": r.previous_status or "-",
            "new_status": r.new_status or "-",
            "assigned_pic": r.assigned_pic or "-",
            "notes": r.notes,
        }
        for r in rows
    ]


@app.get("/api/governance/data-dictionary")
def list_data_dictionary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(DataDictionary).order_by(DataDictionary.id).all()
    return [
        {
            "id": r.id,
            "parameter_code": r.parameter_code,
            "display_name": r.display_name,
            "standard_unit": r.standard_unit,
            "accepted_aliases": r.accepted_aliases,
            "valid_min": r.valid_min,
            "valid_max": r.valid_max,
            "physical_min": r.physical_min,
            "physical_max": r.physical_max,
            "max_step_per_hour": r.max_step_per_hour,
            "persistence_limit": r.persistence_limit,
            "wmo_reference": r.wmo_reference,
            "description": r.description,
        }
        for r in rows
    ]


@app.post("/api/governance/data-dictionary")
def create_data_dictionary(
    payload: DataDictionaryCreate,
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    exists = db.query(DataDictionary).filter(DataDictionary.parameter_code == payload.parameter_code.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="Parameter code sudah terdaftar.")
    item = DataDictionary(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.put("/api/governance/data-dictionary/{dd_id}")
def update_data_dictionary(
    dd_id: int,
    payload: DataDictionaryUpdate,
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    item = db.query(DataDictionary).filter(DataDictionary.id == dd_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entri Data Dictionary tidak ditemukan.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/governance/raci")
def list_raci_registry(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(RaciRegistry).order_by(RaciRegistry.station_code).all()
    return [
        {
            "id": r.id,
            "station_code": r.station_code,
            "station_name": r.station_name,
            "parameter_scope": r.parameter_scope,
            "responsible_role": r.responsible_role,
            "accountable_role": r.accountable_role,
            "consulted_role": r.consulted_role,
            "informed_role": r.informed_role,
            "assigned_pic_username": r.assigned_pic_username,
            "assigned_pic_name": r.assigned_pic_name,
            "sla_hours_critical": r.sla_hours_critical,
            "sla_hours_warning": r.sla_hours_warning,
        }
        for r in rows
    ]


@app.put("/api/governance/raci/{raci_id}")
def update_raci_registry(
    raci_id: int,
    payload: RaciUpdate,
    current_user: User = Depends(require_roles("staf_qc")),
    db: Session = Depends(get_db),
):
    item = db.query(RaciRegistry).filter(RaciRegistry.id == raci_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Entri RACI tidak ditemukan.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/governance/sops")
def list_sop_guides(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SopGuide).order_by(SopGuide.sop_code).all()
    return [
        {
            "id": r.id,
            "sop_code": r.sop_code,
            "violation_type": r.violation_type,
            "parameter_scope": r.parameter_scope,
            "title": r.title,
            "steps": r.steps_text.split("\n"),
            "sla_target_hours": r.sla_target_hours,
            "escalation_target": r.escalation_target,
        }
        for r in rows
    ]


# ==================== STATIC FRONTEND ====================

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")
