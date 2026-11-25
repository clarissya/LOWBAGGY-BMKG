import csv
import io
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

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

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-999", "-999.0", "-9999", "9999", "999.9", "err", "error", "-"}
TIMESTAMP_ALIASES = {"timestamp", "waktu_obs", "datetime_utc", "datetime", "tanggal_jam", "waktu", "obs_time", "date_time", "tgl_jam"}
STATION_ALIASES = {"station_code", "kode_aws", "kode_stasiun", "station_id", "stasiun", "station_name", "nama_stasiun", "station"}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _norm_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")


def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    lower_name = filename.lower()
    if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str)

    # Decode text with BOM handling
    text = file_bytes.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        if sample.count(";") > sample.count(","):
            delimiter = ";"
    df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False)
    return df


def _parse_timestamp(raw_ts: str) -> Optional[datetime]:
    val = str(raw_ts).strip()
    if not val or val.lower() in MISSING_TOKENS:
        return None
    val = val.replace("T", " ").replace("Z", "")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    parsed = pd.to_datetime(val, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def _resolve_station(raw_station: str, stations_by_code: Dict[str, Station], stations_by_name: Dict[str, Station]) -> Tuple[str, str]:
    token = str(raw_station).strip()
    upper = token.upper()
    if upper in stations_by_code:
        st = stations_by_code[upper]
        return st.station_code, st.station_name

    low = token.lower()
    for name_low, st in stations_by_name.items():
        if low == name_low or low in name_low or name_low in low:
            return st.station_code, st.station_name

    # Fuzzy keyword matching for common station short names
    if "kemayoran" in low or "kmy" in low:
        st = stations_by_code.get("AWS-KMY")
        if st:
            return st.station_code, st.station_name
    if "bogor" in low or "bgr" in low:
        st = stations_by_code.get("AWS-BGR")
        if st:
            return st.station_code, st.station_name
    if "priok" in low or "tpr" in low:
        st = stations_by_code.get("AWS-TPR")
        if st:
            return st.station_code, st.station_name

    code = upper[:32] if token else "AWS-UNK"
    return code, token or "Stasiun Tidak Dikenal"


def _parse_numeric(raw_val: str, raw_col_name: str, param_code: str) -> Tuple[Optional[float], str, bool]:
    """Returns (numeric_value, display_raw, is_missing_or_corrupt)."""
    if raw_val is None:
        return None, "NULL", True
    s = str(raw_val).strip()
    if s.lower() in MISSING_TOKENS:
        return None, s if s else "NULL", True

    # Support comma decimal format e.g. "28,4"
    cleaned = s.replace(",", ".")
    try:
        val = float(cleaned)
        if math.isnan(val) or math.isinf(val):
            return None, s, True
    except ValueError:
        return None, s, True

    # Unit normalization: convert knots to m/s if column indicates knots
    if param_code == "wind_speed" and ("kt" in raw_col_name or "knot" in raw_col_name):
        val = round(val * 0.514444, 2)

    return round(val, 3), s, False


def _find_raci(station_code: str, param_code: str, raci_rows: List[RaciRegistry]) -> RaciRegistry:
    for r in raci_rows:
        if r.station_code == station_code and r.parameter_scope == param_code:
            return r
    for r in raci_rows:
        if r.station_code == station_code and r.parameter_scope == "ALL":
            return r
    return raci_rows[0]


def _find_sop(violation_type: str, param_code: str, sop_rows: List[SopGuide]) -> SopGuide:
    for s in sop_rows:
        if s.violation_type == violation_type and s.parameter_scope == param_code:
            return s
    for s in sop_rows:
        if s.violation_type == violation_type and s.parameter_scope == "ALL":
            return s
    return sop_rows[0]


def process_etl_upload(
    db: Session,
    file_bytes: bytes,
    filename: str,
    actor: User,
) -> dict:
    df = _read_dataframe(file_bytes, filename)
    if df.empty:
        raise ValueError(f"File '{filename}' kosong atau tidak memiliki baris data.")

    # Load governance metadata
    dd_list = db.query(DataDictionary).all()
    stations = db.query(Station).all()
    raci_list = db.query(RaciRegistry).all()
    sop_list = db.query(SopGuide).all()

    stations_by_code = {s.station_code.upper(): s for s in stations}
    stations_by_name = {s.station_name.lower(): s for s in stations}

    alias_to_dd: Dict[str, DataDictionary] = {}
    for dd in dd_list:
        alias_to_dd[dd.parameter_code.lower()] = dd
        for alias in dd.accepted_aliases.split(","):
            norm_a = _norm_col(alias)
            if norm_a:
                alias_to_dd[norm_a] = dd

    # Map dataframe columns
    col_map = {_norm_col(c): c for c in df.columns}
    ts_col = next((col_map[c] for c in col_map if c in TIMESTAMP_ALIASES), None)
    st_col = next((col_map[c] for c in col_map if c in STATION_ALIASES), None)

    if not ts_col:
        raise ValueError(
            f"Kolom timestamp tidak ditemukan di '{filename}'. Gunakan salah satu alias: {', '.join(sorted(TIMESTAMP_ALIASES))}"
        )

    # Detect wide parameter columns vs long format
    param_cols: List[Tuple[str, str, DataDictionary]] = []
    for norm_c, orig_c in col_map.items():
        if norm_c in alias_to_dd:
            param_cols.append((norm_c, orig_c, alias_to_dd[norm_c]))

    is_long_format = False
    if not param_cols and "parameter" in col_map and ("value" in col_map or "nilai" in col_map):
        is_long_format = True

    if not param_cols and not is_long_format:
        raise ValueError(
            f"Tidak ada kolom parameter cuaca yang dikenali di Data Dictionary pada file '{filename}'."
        )

    # Build standardized candidate observations
    candidates = []
    fallback_station = filename.split(".")[0].upper()[:16]

    for _, row in df.iterrows():
        obs_time = _parse_timestamp(row[ts_col])
        if obs_time is None:
            obs_time = utcnow().replace(microsecond=0)
            ts_corrupt = True
        else:
            ts_corrupt = False

        raw_st = row[st_col] if st_col else fallback_station
        station_code, station_name = _resolve_station(raw_st, stations_by_code, stations_by_name)

        if is_long_format:
            p_raw = _norm_col(row[col_map["parameter"]])
            val_col = col_map.get("value") or col_map.get("nilai")
            dd = alias_to_dd.get(p_raw)
            if dd:
                num_val, disp_raw, is_miss = _parse_numeric(row[val_col], p_raw, dd.parameter_code)
                candidates.append(
                    {
                        "observed_at": obs_time,
                        "ts_corrupt": ts_corrupt,
                        "station_code": station_code,
                        "station_name": station_name,
                        "dd": dd,
                        "raw_value": disp_raw,
                        "numeric_value": num_val,
                        "is_missing": is_miss,
                    }
                )
        else:
            for norm_c, orig_c, dd in param_cols:
                num_val, disp_raw, is_miss = _parse_numeric(row[orig_c], norm_c, dd.parameter_code)
                candidates.append(
                    {
                        "observed_at": obs_time,
                        "ts_corrupt": ts_corrupt,
                        "station_code": station_code,
                        "station_name": station_name,
                        "dd": dd,
                        "raw_value": disp_raw,
                        "numeric_value": num_val,
                        "is_missing": is_miss,
                    }
                )

    if not candidates:
        raise ValueError(f"Tidak ada baris observasi yang dapat diproses dari '{filename}'.")

    # Sort chronologically per station & parameter for temporal WMO-No. 8 checks
    candidates.sort(key=lambda x: (x["station_code"], x["dd"].parameter_code, x["observed_at"]))

    # Fetch recent historical valid numeric values from DB per (station, param) for continuity
    last_seen: Dict[Tuple[str, str], Tuple[datetime, float, int]] = {}
    recent_records = (
        db.query(ObservationRecord)
        .filter(ObservationRecord.numeric_value.isnot(None))
        .order_by(ObservationRecord.observed_at.desc())
        .limit(500)
        .all()
    )
    for rec in reversed(recent_records):
        key = (rec.station_code, rec.parameter_code)
        prev = last_seen.get(key)
        if prev and prev[1] == rec.numeric_value:
            last_seen[key] = (rec.observed_at, rec.numeric_value, prev[2] + 1)
        else:
            last_seen[key] = (rec.observed_at, rec.numeric_value, 1)

    now = utcnow()
    batch_code = f"ETL-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
    batch = EtlBatch(
        batch_code=batch_code,
        filename=filename,
        uploaded_by=actor.username,
        uploaded_at=now,
    )
    db.add(batch)
    db.flush()

    valid_count = 0
    warning_count = 0
    critical_count = 0
    new_cases = 0
    stations_seen = set()

    for item in candidates:
        dd: DataDictionary = item["dd"]
        scode = item["station_code"]
        sname = item["station_name"]
        stations_seen.add(scode)
        val = item["numeric_value"]
        raw_v = item["raw_value"]
        obs_at = item["observed_at"]
        key = (scode, dd.parameter_code)

        qc_status = "Valid"
        qc_rule = None
        qc_detail = "Lolos seluruh validasi skema dan kualitas WMO-No. 8."
        schema_valid = True

        # 1. Missing Data / Corrupt Schema Check
        if item["ts_corrupt"]:
            qc_status = "Critical/Missing"
            qc_rule = "Missing Data"
            qc_detail = f"Format timestamp observasi tidak valid/korup pada {sname} ({dd.display_name})."
            schema_valid = False
        elif item["is_missing"] or val is None:
            qc_status = "Critical/Missing"
            qc_rule = "Missing Data"
            qc_detail = f"Data {dd.display_name} hilang/kosong atau bernilai sentinel ('{raw_v}')."
            schema_valid = False
        else:
            # 2. Gross Range Check (Physical & Climatological)
            if val < dd.physical_min or val > dd.physical_max:
                qc_status = "Critical/Missing"
                qc_rule = "Range Check"
                qc_detail = (
                    f"Nilai {val} {dd.standard_unit} melampaui batas fisik WMO "
                    f"[{dd.physical_min}, {dd.physical_max}] {dd.standard_unit}."
                )
                schema_valid = False
            elif val < dd.valid_min or val > dd.valid_max:
                qc_status = "Warning/Suspect"
                qc_rule = "Range Check"
                qc_detail = (
                    f"Nilai {val} {dd.standard_unit} di luar batas wajar klimatologis "
                    f"[{dd.valid_min}, {dd.valid_max}] {dd.standard_unit}."
                )
            else:
                # 3. Temporal Step Check & Persistence Check
                prev = last_seen.get(key)
                if prev is not None:
                    prev_time, prev_val, streak = prev
                    hours_diff = (obs_at - prev_time).total_seconds() / 3600.0
                    if 0 < hours_diff <= 3.0:
                        step_rate = abs(val - prev_val) / max(hours_diff, 1.0)
                        if step_rate > dd.max_step_per_hour * 1.8:
                            qc_status = "Critical/Missing"
                            qc_rule = "Step Check"
                            qc_detail = (
                                f"Lonjakan ekstrem {abs(val - prev_val):.2f} {dd.standard_unit} "
                                f"(dari {prev_val} ke {val} dalam {hours_diff:.1f} jam; batas {dd.max_step_per_hour}/jam)."
                            )
                        elif step_rate > dd.max_step_per_hour:
                            qc_status = "Warning/Suspect"
                            qc_rule = "Step Check"
                            qc_detail = (
                                f"Lonjakan drastis {abs(val - prev_val):.2f} {dd.standard_unit} "
                                f"(dari {prev_val} ke {val} dalam {hours_diff:.1f} jam; batas {dd.max_step_per_hour}/jam)."
                            )

                    # Persistence Check (exclude rainfall == 0.0)
                    if val == prev_val and not (dd.parameter_code == "rainfall" and val == 0.0):
                        new_streak = streak + 1
                    else:
                        new_streak = 1

                    if qc_status == "Valid":
                        if new_streak >= dd.persistence_limit + 2:
                            qc_status = "Critical/Missing"
                            qc_rule = "Persistence Check"
                            qc_detail = (
                                f"Sensor macet: nilai konstan {val} {dd.standard_unit} berulang "
                                f"{new_streak} kali berturut-turut (batas kritis {dd.persistence_limit + 2})."
                            )
                        elif new_streak >= dd.persistence_limit:
                            qc_status = "Warning/Suspect"
                            qc_rule = "Persistence Check"
                            qc_detail = (
                                f"Indikasi sensor macet: nilai konstan {val} {dd.standard_unit} berulang "
                                f"{new_streak} kali berturut-turut (batas {dd.persistence_limit})."
                            )
                    last_seen[key] = (obs_at, val, new_streak)
                else:
                    last_seen[key] = (obs_at, val, 1)

        if qc_status == "Valid":
            valid_count += 1
        elif qc_status == "Warning/Suspect":
            warning_count += 1
        else:
            critical_count += 1

        obs_rec = ObservationRecord(
            batch_id=batch.id,
            observed_at=obs_at,
            station_code=scode,
            station_name=sname,
            parameter_code=dd.parameter_code,
            parameter_name=dd.display_name,
            raw_value=raw_v,
            numeric_value=val,
            unit=dd.standard_unit,
            qc_status=qc_status,
            qc_rule_triggered=qc_rule,
            qc_detail=qc_detail,
            schema_valid=schema_valid,
            created_at=now,
        )
        db.add(obs_rec)
        db.flush()

        if qc_status != "Valid":
            raci = _find_raci(scode, dd.parameter_code, raci_list)
            sop = _find_sop(qc_rule or "Missing Data", dd.parameter_code, sop_list)
            sla_hours = raci.sla_hours_critical if qc_status == "Critical/Missing" else raci.sla_hours_warning
            case_code = f"ANM-{now.strftime('%y%m%d')}-{obs_rec.id:04d}"

            case = AnomalyCase(
                case_code=case_code,
                observation_id=obs_rec.id,
                station_code=scode,
                station_name=sname,
                parameter_code=dd.parameter_code,
                parameter_name=dd.display_name,
                observed_at=obs_at,
                raw_value=raw_v,
                severity=qc_status,
                violation_type=qc_rule or "Missing Data",
                diagnostic_message=qc_detail,
                data_owner=raci.accountable_role,
                data_steward=raci.consulted_role,
                responsible_unit=raci.responsible_role,
                assigned_pic_username=raci.assigned_pic_username,
                assigned_pic_name=raci.assigned_pic_name,
                sop_code=sop.sop_code,
                status="Open",
                sla_due_at=now + timedelta(hours=sla_hours),
                is_escalated=False,
                detected_at=now,
                updated_at=now,
            )
            db.add(case)
            db.flush()
            new_cases += 1

            db.add(
                AuditTrail(
                    audit_code=f"AUD-{uuid.uuid4().hex[:8].upper()}",
                    case_id=case.id,
                    case_code=case_code,
                    event_time=now,
                    actor_username=actor.username,
                    actor_name=actor.full_name,
                    actor_role=actor.role,
                    action_type="DETECTED",
                    previous_status=None,
                    new_status="Open",
                    assigned_pic=raci.assigned_pic_name,
                    notes=(
                        f"[{qc_rule}] Terdeteksi pada {sname} ({dd.display_name}={raw_v}). "
                        f"Otomatis ditugaskan ke {raci.assigned_pic_name} ({raci.responsible_role})."
                    ),
                )
            )

    batch.total_rows = len(candidates)
    batch.valid_count = valid_count
    batch.warning_count = warning_count
    batch.critical_count = critical_count
    batch.stations_detected = ", ".join(sorted(stations_seen))

    db.add(
        AuditTrail(
            audit_code=f"AUD-{uuid.uuid4().hex[:8].upper()}",
            case_id=None,
            case_code=None,
            event_time=now,
            actor_username=actor.username,
            actor_name=actor.full_name,
            actor_role=actor.role,
            action_type="ETL_IMPORT",
            previous_status=None,
            new_status="COMPLETED",
            assigned_pic="-",
            notes=(
                f"Unggah ETL '{filename}' ({batch_code}): {len(candidates)} observasi distandarkan "
                f"(Valid: {valid_count}, Warning: {warning_count}, Critical/Missing: {critical_count})."
            ),
        )
    )

    db.commit()

    return {
        "batch_code": batch.batch_code,
        "filename": batch.filename,
        "uploaded_at": batch.uploaded_at.isoformat(),
        "total_rows": batch.total_rows,
        "valid_count": batch.valid_count,
        "warning_count": batch.warning_count,
        "critical_count": batch.critical_count,
        "new_anomaly_cases": new_cases,
        "stations_detected": sorted(stations_seen),
    }
