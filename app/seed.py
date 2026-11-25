from datetime import datetime, timedelta, timezone
import math
from sqlalchemy.orm import Session

from app.auth import hash_password
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


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_reference_data(db: Session) -> None:
    """Seed BMKG users (Datin, Observer, Forecaster, Manajemen), maritime/synoptic stations, WMO Data Dictionary, RACI & Blueprint SOPs."""
    if db.query(User).count() == 0:
        users = [
            User(
                username="datin.qc",
                password_hash=hash_password("bmkg123"),
                full_name="Rina Kusuma, S.Stat",
                role="staf_qc",
                unit_name="Bidang Datin (Data & Informasi) - UPT Tanjung Perak",
                assigned_station_code=None,
            ),
            User(
                username="observer.tprk",
                password_hash=hash_password("bmkg123"),
                full_name="Budi Santoso, S.T.",
                role="teknisi",
                unit_name="Unit Observer & Teknisi AWS - Stamar Tanjung Perak",
                assigned_station_code="AWS-TPRK",
            ),
            User(
                username="observer.tuban",
                password_hash=hash_password("bmkg123"),
                full_name="Andi Wijaya, A.Md",
                role="teknisi",
                unit_name="Unit Observer & Teknisi AWS - Maritim Tuban",
                assigned_station_code="AWS-TBN",
            ),
            User(
                username="forecaster",
                password_hash=hash_password("bmkg123"),
                full_name="Fajar Nugroho, S.Tr.Met",
                role="forecaster",
                unit_name="Bidang Forecaster / Prakiraan Maritim - UPT Tanjung Perak",
                assigned_station_code=None,
            ),
            User(
                username="manajemen",
                password_hash=hash_password("bmkg123"),
                full_name="Dr. Hendra Pratama",
                role="manajemen",
                unit_name="Kepala UPT Stasiun Meteorologi Maritim Tanjung Perak",
                assigned_station_code=None,
            ),
        ]
        db.add_all(users)

    if db.query(Station).count() == 0:
        stations = [
            Station(
                station_code="AWS-TPRK",
                station_name="Stasiun Meteorologi Maritim Tanjung Perak (Surabaya)",
                region="Jawa Timur",
                station_type="AWS Maritim (10-Menit & 1-Jam)",
                latitude=-7.2097,
                longitude=112.7351,
            ),
            Station(
                station_code="AWS-TBN",
                station_name="AWS Maritim Pelabuhan Tuban",
                region="Jawa Timur",
                station_type="AWS Maritim (1-Jam)",
                latitude=-6.8946,
                longitude=112.0496,
            ),
            Station(
                station_code="AWS-LMG",
                station_name="AWS Maritim Brondong (Lamongan)",
                region="Jawa Timur",
                station_type="AWS Maritim (1-Jam)",
                latitude=-6.8722,
                longitude=112.2836,
            ),
        ]
        db.add_all(stations)

    if db.query(DataDictionary).count() == 0:
        dd_items = [
            DataDictionary(
                parameter_code="temperature",
                display_name="Suhu Udara (T2M)",
                standard_unit="°C",
                accepted_aliases="temperature,temp,temp_c,suhu,suhu_udara,t2m,ta,air_temp",
                valid_min=18.0,
                valid_max=39.0,
                physical_min=-10.0,
                physical_max=50.0,
                max_step_per_hour=6.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 2",
                description="Suhu udara permukaan; lonjakan mendadak (misal 25°C -> 35°C dalam 1 jam) otomatis ditandai Step Check.",
            ),
            DataDictionary(
                parameter_code="humidity",
                display_name="Kelembaban Relatif (RH)",
                standard_unit="%",
                accepted_aliases="humidity,rh,rh_pct,rh2m,kelembaban,kelembaban_udara,rel_humidity",
                valid_min=25.0,
                valid_max=100.0,
                physical_min=0.0,
                physical_max=100.0,
                max_step_per_hour=30.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 4",
                description="Kelembaban udara relatif permukaan dalam persen (%).",
            ),
            DataDictionary(
                parameter_code="rainfall",
                display_name="Curah Hujan (RR)",
                standard_unit="mm",
                accepted_aliases="rainfall,rain,rain_mm,curah_hujan,precip,precipitation,rr,ch",
                valid_min=0.0,
                valid_max=150.0,
                physical_min=0.0,
                physical_max=300.0,
                max_step_per_hour=120.0,
                persistence_limit=5,
                wmo_reference="WMO-No. 8 Part I Ch. 6",
                description="Akumulasi curah hujan (nilai 0 mm dikecualikan dari persistence check saat cuaca cerah).",
            ),
            DataDictionary(
                parameter_code="wind_speed",
                display_name="Kecepatan Angin (WS)",
                standard_unit="knots",
                accepted_aliases="wind_speed,wind,wind_kt,wind_knots,wind_ms,kec_angin,kec_angin_ms,ws10m,ff,kecepatan_angin",
                valid_min=0.0,
                valid_max=58.0,
                physical_min=0.0,
                physical_max=145.0,
                max_step_per_hour=30.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 5 (Standar Maritim Knots)",
                description="Standar layanan maritim BMKG dalam knots (data mentah m/s dikonversi otomatis × 1.94384 ke knots).",
            ),
            DataDictionary(
                parameter_code="pressure",
                display_name="Tekanan Udara (SLP/mb)",
                standard_unit="hPa",
                accepted_aliases="pressure,press,press_hpa,press_mb,tekanan,tekanan_udara,slp,qff,mslp",
                valid_min=995.0,
                valid_max=1025.0,
                physical_min=870.0,
                physical_max=1085.0,
                max_step_per_hour=5.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 3",
                description="Tekanan atmosfer permukaan laut dalam hPa/mb; lompatan tajam misal 1010 -> 1020 mb/jam ditandai Step Check.",
            ),
        ]
        db.add_all(dd_items)

    if db.query(RaciRegistry).count() == 0:
        raci_items = [
            RaciRegistry(
                station_code="AWS-TPRK",
                station_name="Stasiun Meteorologi Maritim Tanjung Perak (Surabaya)",
                parameter_scope="ALL",
                responsible_role="Observer & Teknisi AWS (Stamar Tanjung Perak)",
                accountable_role="Bidang Datin & Kepala UPT Tanjung Perak (Data Owner)",
                consulted_role="Bidang Datin (QC & Arsip 10-Menit) + Forecaster",
                informed_role="Forecaster Maritim & BMKG Pusat",
                assigned_pic_username="observer.tprk",
                assigned_pic_name="Budi Santoso, S.T.",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
            RaciRegistry(
                station_code="AWS-TBN",
                station_name="AWS Maritim Pelabuhan Tuban",
                parameter_scope="ALL",
                responsible_role="Observer & Teknisi AWS (Maritim Tuban)",
                accountable_role="Bidang Datin & Kepala UPT Tanjung Perak (Data Owner)",
                consulted_role="Bidang Datin (QC & Arsip) + Forecaster",
                informed_role="Forecaster Maritim & BMKG Pusat",
                assigned_pic_username="observer.tuban",
                assigned_pic_name="Andi Wijaya, A.Md",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
            RaciRegistry(
                station_code="AWS-LMG",
                station_name="AWS Maritim Brondong (Lamongan)",
                parameter_scope="ALL",
                responsible_role="Observer & Teknisi AWS (Wilayah Lamongan-Surabaya)",
                accountable_role="Bidang Datin & Kepala UPT Tanjung Perak (Data Owner)",
                consulted_role="Bidang Datin (QC & Arsip) + Forecaster",
                informed_role="Forecaster Maritim & BMKG Pusat",
                assigned_pic_username="observer.tprk",
                assigned_pic_name="Budi Santoso, S.T.",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
        ]
        db.add_all(raci_items)

    if db.query(SopGuide).count() == 0:
        sops = [
            SopGuide(
                sop_code="USULAN-SOP-01",
                violation_type="Missing Data",
                parameter_scope="ALL",
                title="Rancangan SOP Penanganan Data Hilang / Telemetri Kosong (Observer → Datin)",
                steps_text=(
                    "1. Datin / Forecaster mengonfirmasi gap data pada arsip 10-menit lokal maupun umpan 1-jam pusat.\n"
                    "2. Observer memeriksa catu daya, modem telemetri AWS, dan melakukan pengunduhan ulang (backfill) memori logger.\n"
                    "3. Jika sensor gagal merekam, Observer menyuplai data pengamatan sinoptik manual terdekat sebagai pembanding.\n"
                    "4. Datin memverifikasi hasil backfill sebelum data digunakan kembali oleh Forecaster untuk model prakiraan."
                ),
                sla_target_hours=4,
                escalation_target="Koordinator Datin & Kepala UPT Tanjung Perak",
            ),
            SopGuide(
                sop_code="USULAN-SOP-02",
                violation_type="Range Check",
                parameter_scope="ALL",
                title="Rancangan SOP Penanganan Nilai di Luar Batas Wajar (Gross Range Check WMO-No. 8)",
                steps_text=(
                    "1. Datin dan Forecaster membandingkan nilai suspect dengan stasiun tetangga (misal Tuban vs Tanjung Perak) serta citra radar/satelit.\n"
                    "2. Observer melakukan pengecekan fisik sensor AWS (radiasi shield, corong curah hujan, konektor sinyal).\n"
                    "3. Lakukan uji pembacaan pembanding di lapangan; jika sensor menyimpang, lakukan kalibrasi atau penggantian.\n"
                    "4. Catat hasil perbaikan dan konfirmasi ke Datin agar data ditandai Resolved / Verified."
                ),
                sla_target_hours=12,
                escalation_target="Koordinator Datin & Unit Pemeliharaan Peralatan",
            ),
            SopGuide(
                sop_code="USULAN-SOP-03",
                violation_type="Step Check",
                parameter_scope="ALL",
                title="Rancangan SOP Penanganan Lonjakan Drastis Antar Jam (Temporal Step Check)",
                steps_text=(
                    "1. Forecaster memeriksa grafik tendensi 24 jam & citra radar cuaca untuk memastikan apakah lonjakan dipicu fenomena cuaca ekstrem (squall line/badai).\n"
                    "2. Jika tidak ada konfirmasi cuaca ekstrem di radar, Forecaster mengembalikan data ke Datin sebagai Suspect.\n"
                    "3. Observer memeriksa kestabilan tegangan/grounding data logger AWS untuk mencegah electrical spike.\n"
                    "4. Datin melakukan koreksi flag sebelum data dipakai dalam model estimasi wilayah sekitar."
                ),
                sla_target_hours=12,
                escalation_target="Koordinator Datin & Kepala Seksi Observasi",
            ),
            SopGuide(
                sop_code="USULAN-SOP-04",
                violation_type="Persistence Check",
                parameter_scope="ALL",
                title="Rancangan SOP Penanganan Sensor Macet / Nilai Konstan (Persistence Check)",
                steps_text=(
                    "1. Datin memverifikasi deret waktu 10-menit/1-jam yang menunjukkan nilai identik berturut-turut.\n"
                    "2. Observer memeriksa kondisi mekanik sensor (baling-baling anemometer macet atau sensor RH jenuh).\n"
                    "3. Lakukan pembersihan mekanik dan restart modul akuisisi pada logger AWS.\n"
                    "4. Konfirmasi pembacaan kembali dinamis sebelum status diubah menjadi Resolved."
                ),
                sla_target_hours=8,
                escalation_target="Koordinator Datin & Kepala UPT",
            ),
        ]
        db.add_all(sops)

    db.commit()


def seed_baseline_observations(db: Session) -> None:
    """Seed realistic 24-hour coastal maritime time-series data across Tanjung Perak, Tuban & Lamongan so tendency charts & dashboard work on launch."""
    if db.query(ObservationRecord).count() > 0:
        return

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    batch = EtlBatch(
        batch_code="ETL-BASELINE-MARITIM",
        filename="baseline_aws_maritim_24h.csv",
        uploaded_by="datin.qc",
        uploaded_at=now - timedelta(hours=1),
        interval_type="1h",
        total_rows=0,
        valid_count=0,
        warning_count=0,
        critical_count=0,
        stations_detected="AWS-TPRK, AWS-TBN, AWS-LMG",
    )
    db.add(batch)
    db.flush()

    db.add(
        AuditTrail(
            audit_code="AUD-BASE-0001",
            case_id=None,
            case_code=None,
            event_time=now - timedelta(hours=1),
            actor_username="datin.qc",
            actor_name="Rina Kusuma, S.Stat",
            actor_role="staf_qc",
            action_type="ETL_IMPORT",
            previous_status=None,
            new_status="COMPLETED",
            assigned_pic="-",
            notes="Inisialisasi data historis 24 jam dari 3 AWS Maritim (Tanjung Perak, Tuban, Lamongan).",
        )
    )

    raci_map = {r.station_code: r for r in db.query(RaciRegistry).all()}
    sop_map = {s.violation_type: s for s in db.query(SopGuide).all()}

    stations_meta = [
        ("AWS-TPRK", "Stasiun Meteorologi Maritim Tanjung Perak (Surabaya)"),
        ("AWS-TBN", "AWS Maritim Pelabuhan Tuban"),
        ("AWS-LMG", "AWS Maritim Brondong (Lamongan)"),
    ]

    total_rows = 0
    valid_cnt = 0
    warn_cnt = 0
    crit_cnt = 0
    case_idx = 1

    # Generate 24 hours of realistic hourly temperature & pressure + wind (knots) for 3 maritime stations
    for h_offset in range(23, -1, -1):
        obs_time = now - timedelta(hours=h_offset)
        diurnal = math.sin((obs_time.hour - 8) * math.pi / 12.0)
        for st_idx, (scode, sname) in enumerate(stations_meta):
            base_temp = round(28.5 + 3.2 * diurnal + st_idx * 0.3, 1)
            base_press = round(1010.5 - 1.2 * diurnal + st_idx * 0.2, 1)
            base_wind = round(11.0 + 3.0 * max(0, diurnal) + st_idx * 1.1, 1)  # in knots

            # Inject 3 realistic anomalies matching Pak Fajar's examples
            temp_val, temp_raw, temp_status, temp_rule, temp_detail, temp_svalid = (
                base_temp, str(base_temp), "Valid", None, "Lolos seluruh validasi WMO-No. 8", True
            )
            if scode == "AWS-TPRK" and h_offset == 5:
                temp_val, temp_raw = 37.8, "37.8"
                temp_status = "Warning/Suspect"
                temp_rule = "Step Check"
                temp_detail = "Lonjakan suhu drastis > 6.0 °C/jam (mirip kasus lonjakan 25°C -> 35°C) — perlu cek tendensi."

            press_val, press_raw, press_status, press_rule, press_detail, press_svalid = (
                base_press, str(base_press), "Valid", None, "Lolos seluruh validasi WMO-No. 8", True
            )
            if scode == "AWS-TBN" and h_offset == 4:
                press_val, press_raw = 1020.4, "1020.4"
                press_status = "Critical/Missing"
                press_rule = "Step Check"
                press_detail = "Lonjakan tekanan udara ekstrem > 9.0 hPa/jam (dari ~1010 ke 1020.4 mb)."

            wind_val, wind_raw, wind_status, wind_rule, wind_detail, wind_svalid = (
                base_wind, str(base_wind), "Valid", None, "Lolos seluruh validasi WMO-No. 8", True
            )
            if scode == "AWS-LMG" and h_offset == 2:
                wind_val, wind_raw = None, "NULL"
                wind_status = "Critical/Missing"
                wind_rule = "Missing Data"
                wind_detail = "Data kecepatan angin (knots) hilang / bernilai NULL pada telemetri AWS."
                wind_svalid = False

            records_to_add = [
                ("temperature", "Suhu Udara (T2M)", temp_raw, temp_val, "°C", temp_status, temp_rule, temp_detail, temp_svalid),
                ("pressure", "Tekanan Udara (SLP/mb)", press_raw, press_val, "hPa", press_status, press_rule, press_detail, press_svalid),
                ("wind_speed", "Kecepatan Angin (WS)", wind_raw, wind_val, "knots", wind_status, wind_rule, wind_detail, wind_svalid),
            ]

            for pcode, pname, rval, nval, unit, qst, qrule, qdet, sv in records_to_add:
                rec = ObservationRecord(
                    batch_id=batch.id,
                    observed_at=obs_time,
                    interval_type="1h",
                    station_code=scode,
                    station_name=sname,
                    parameter_code=pcode,
                    parameter_name=pname,
                    raw_value=rval,
                    numeric_value=nval,
                    unit=unit,
                    qc_status=qst,
                    qc_rule_triggered=qrule,
                    qc_detail=qdet,
                    schema_valid=sv,
                    created_at=now - timedelta(hours=1),
                )
                db.add(rec)
                db.flush()
                total_rows += 1
                if qst == "Valid":
                    valid_cnt += 1
                elif qst == "Warning/Suspect":
                    warn_cnt += 1
                else:
                    crit_cnt += 1

                if qst != "Valid":
                    raci = raci_map[scode]
                    sop = sop_map[qrule]
                    is_resolved = case_idx == 1
                    case_code = f"ANM-BASE-{case_idx:04d}"
                    sla_hours = raci.sla_hours_critical if qst == "Critical/Missing" else raci.sla_hours_warning
                    case = AnomalyCase(
                        case_code=case_code,
                        observation_id=rec.id,
                        station_code=scode,
                        station_name=sname,
                        parameter_code=pcode,
                        parameter_name=pname,
                        observed_at=obs_time,
                        raw_value=rval,
                        severity=qst,
                        violation_type=qrule,
                        diagnostic_message=qdet,
                        data_owner=raci.accountable_role,
                        data_steward=raci.consulted_role,
                        responsible_unit=raci.responsible_role,
                        assigned_pic_username=raci.assigned_pic_username,
                        assigned_pic_name=raci.assigned_pic_name,
                        sop_code=sop.sop_code,
                        status="Resolved" if is_resolved else "Open",
                        resolution_notes="Dikonfirmasi Forecaster & Datin; grounding sensor suhu diperbaiki Observer." if is_resolved else None,
                        sla_due_at=(now - timedelta(hours=1)) + timedelta(hours=sla_hours),
                        is_escalated=False,
                        detected_at=now - timedelta(hours=1),
                        updated_at=now if is_resolved else now - timedelta(hours=1),
                        resolved_at=now if is_resolved else None,
                    )
                    db.add(case)
                    db.flush()

                    db.add(
                        AuditTrail(
                            audit_code=f"AUD-BASE-C{case_idx:03d}A",
                            case_id=case.id,
                            case_code=case_code,
                            event_time=now - timedelta(hours=1),
                            actor_username="system.qc",
                            actor_name="Mesin QC Otomatis (WMO-No. 8)",
                            actor_role="system",
                            action_type="DETECTED",
                            previous_status=None,
                            new_status="Open",
                            assigned_pic=raci.assigned_pic_name,
                            notes=f"Anomali {qrule} terdeteksi pada {sname} ({pname}={rval}). Otomatis ditugaskan ke {raci.assigned_pic_name}.",
                        )
                    )
                    if is_resolved:
                        db.add(
                            AuditTrail(
                                audit_code=f"AUD-BASE-C{case_idx:03d}B",
                                case_id=case.id,
                                case_code=case_code,
                                event_time=now,
                                actor_username=raci.assigned_pic_username,
                                actor_name=raci.assigned_pic_name,
                                actor_role="teknisi",
                                action_type="STATUS_CHANGE",
                                previous_status="Open",
                                new_status="Resolved",
                                assigned_pic=raci.assigned_pic_name,
                                notes="Dikonfirmasi Forecaster & Datin; grounding sensor suhu diperbaiki Observer.",
                            )
                        )
                    case_idx += 1

    batch.total_rows = total_rows
    batch.valid_count = valid_cnt
    batch.warning_count = warn_cnt
    batch.critical_count = crit_cnt
    db.commit()
