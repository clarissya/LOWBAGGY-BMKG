from datetime import datetime, timedelta, timezone
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
    """Seed users, stations, WMO Data Dictionary, RACI matrix, and SOP guides if empty."""
    if db.query(User).count() == 0:
        users = [
            User(
                username="qc.datin",
                password_hash=hash_password("bmkg123"),
                full_name="Rina Kusuma, S.Stat",
                role="staf_qc",
                unit_name="Unit Pengolahan Data & QC (Datin)",
                assigned_station_code=None,
            ),
            User(
                username="teknisi.obs",
                password_hash=hash_password("bmkg123"),
                full_name="Budi Santoso, S.T.",
                role="teknisi",
                unit_name="Unit Observasi & Kalibrasi AWS",
                assigned_station_code="AWS-KMY",
            ),
            User(
                username="teknisi.bogor",
                password_hash=hash_password("bmkg123"),
                full_name="Andi Wijaya, A.Md",
                role="teknisi",
                unit_name="Unit Observasi Staklim Bogor",
                assigned_station_code="AWS-BGR",
            ),
            User(
                username="manajemen",
                password_hash=hash_password("bmkg123"),
                full_name="Dr. Hendra Pratama",
                role="manajemen",
                unit_name="Deputi Bidang Instrumentasi & Manajemen Data",
                assigned_station_code=None,
            ),
        ]
        db.add_all(users)

    if db.query(Station).count() == 0:
        stations = [
            Station(
                station_code="AWS-KMY",
                station_name="Stasiun Meteorologi Kemayoran",
                region="DKI Jakarta",
                station_type="AWS Synoptic",
                latitude=-6.1556,
                longitude=106.8403,
            ),
            Station(
                station_code="AWS-BGR",
                station_name="Stasiun Klimatologi Bogor",
                region="Jawa Barat",
                station_type="AWS Klimatologi",
                latitude=-6.5067,
                longitude=106.7501,
            ),
            Station(
                station_code="AWS-TPR",
                station_name="Stasiun Meteorologi Maritim Tanjung Priok",
                region="DKI Jakarta",
                station_type="AWS Maritim",
                latitude=-6.1078,
                longitude=106.8806,
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
                valid_min=10.0,
                valid_max=40.0,
                physical_min=-10.0,
                physical_max=50.0,
                max_step_per_hour=7.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 2",
                description="Suhu udara permukaan pada ketinggian 1.25–2 m di atas permukaan tanah.",
            ),
            DataDictionary(
                parameter_code="humidity",
                display_name="Kelembaban Relatif (RH)",
                standard_unit="%",
                accepted_aliases="humidity,rh,rh_pct,rh2m,kelembaban,kelembaban_udara,rel_humidity",
                valid_min=20.0,
                valid_max=100.0,
                physical_min=0.0,
                physical_max=100.0,
                max_step_per_hour=35.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 4",
                description="Persentase rasio tekanan uap air aktual terhadap tekanan uap jenuh.",
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
                description="Akumulasi presipitasi cair per jam (nilai 0 mm dikecualikan dari persistence check).",
            ),
            DataDictionary(
                parameter_code="wind_speed",
                display_name="Kecepatan Angin (WS)",
                standard_unit="m/s",
                accepted_aliases="wind_speed,wind,wind_ms,wind_kt,kec_angin,ws10m,ff,kecepatan_angin",
                valid_min=0.0,
                valid_max=30.0,
                physical_min=0.0,
                physical_max=75.0,
                max_step_per_hour=18.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 5",
                description="Kecepatan angin rata-rata 10 menit pada ketinggian 10 m (konversi otomatis dari knot ke m/s).",
            ),
            DataDictionary(
                parameter_code="pressure",
                display_name="Tekanan Udara (SLP/QFF)",
                standard_unit="hPa",
                accepted_aliases="pressure,press,press_hpa,tekanan,tekanan_udara,slp,qff,mslp",
                valid_min=985.0,
                valid_max=1030.0,
                physical_min=870.0,
                physical_max=1085.0,
                max_step_per_hour=6.0,
                persistence_limit=4,
                wmo_reference="WMO-No. 8 Part I Ch. 3",
                description="Tekanan atmosfer terkoreksi permukaan laut dalam satuan hektopaskal.",
            ),
        ]
        db.add_all(dd_items)

    if db.query(RaciRegistry).count() == 0:
        raci_items = [
            RaciRegistry(
                station_code="AWS-KMY",
                station_name="Stasiun Meteorologi Kemayoran",
                parameter_scope="ALL",
                responsible_role="Teknisi Unit Observasi (AWS Kemayoran)",
                accountable_role="Kepala Stasiun Meteorologi Kemayoran (Data Owner)",
                consulted_role="Staf QC / Datin (Data Steward)",
                informed_role="Manajemen / Deputi Observasi",
                assigned_pic_username="teknisi.obs",
                assigned_pic_name="Budi Santoso, S.T.",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
            RaciRegistry(
                station_code="AWS-BGR",
                station_name="Stasiun Klimatologi Bogor",
                parameter_scope="ALL",
                responsible_role="Teknisi Unit Observasi (Staklim Bogor)",
                accountable_role="Kepala Stasiun Klimatologi Bogor (Data Owner)",
                consulted_role="Staf QC / Datin (Data Steward)",
                informed_role="Manajemen / Deputi Observasi",
                assigned_pic_username="teknisi.bogor",
                assigned_pic_name="Andi Wijaya, A.Md",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
            RaciRegistry(
                station_code="AWS-TPR",
                station_name="Stasiun Meteorologi Maritim Tanjung Priok",
                parameter_scope="ALL",
                responsible_role="Teknisi Unit Observasi (Maritim Tanjung Priok)",
                accountable_role="Kepala Stasiun Maritim Tanjung Priok (Data Owner)",
                consulted_role="Staf QC / Datin (Data Steward)",
                informed_role="Manajemen / Deputi Observasi",
                assigned_pic_username="teknisi.obs",
                assigned_pic_name="Budi Santoso, S.T.",
                sla_hours_critical=4,
                sla_hours_warning=24,
            ),
        ]
        db.add_all(raci_items)

    if db.query(SopGuide).count() == 0:
        sops = [
            SopGuide(
                sop_code="SOP-QC-01",
                violation_type="Missing Data",
                parameter_scope="ALL",
                title="SOP Penanganan Data Hilang / Null / Format Korup (AWS Telemetry Gap)",
                steps_text=(
                    "1. Periksa status koneksi modem/GSM dan catu daya (panel surya/baterai) pada data logger AWS.\n"
                    "2. Lakukan unduh ulang (backfill) log lokal dari memori internal data logger stasiun.\n"
                    "3. Jika sensor terputus secara fisik, periksa kabel sinyal RS-485/SDI-12 dan konektor.\n"
                    "4. Unggah data backfill terverifikasi ke Staf QC Datin dan catat nomor seri logger yang diperbaiki."
                ),
                sla_target_hours=4,
                escalation_target="Kepala Stasiun & Koordinator Datin Pusat",
            ),
            SopGuide(
                sop_code="SOP-QC-02",
                violation_type="Range Check",
                parameter_scope="ALL",
                title="SOP Penanganan Nilai Melampaui Batas Wajar (Gross Range Error WMO-No. 8)",
                steps_text=(
                    "1. Bandingkan nilai ekstrem dengan stasiun referensi terdekat dan pengamatan sinoptik manual.\n"
                    "2. Periksa kondisi fisik sensor (radiasi berlebih, penyumbatan corong tipping bucket, atau korosi konektor).\n"
                    "3. Lakukan uji kalibrasi lapangan menggunakan alat ukur standar portabel.\n"
                    "4. Apabila sensor menyimpang > toleransi WMO, tandai data sebagai Suspect/Invalid dan jadwalkan penggantian sensor."
                ),
                sla_target_hours=12,
                escalation_target="Kepala Subbidang Kalibrasi & Instrumentasi",
            ),
            SopGuide(
                sop_code="SOP-QC-03",
                violation_type="Step Check",
                parameter_scope="ALL",
                title="SOP Penanganan Lonjakan Nilai Drastis (Temporal Step / Spike Check)",
                steps_text=(
                    "1. Verifikasi apakah terjadi fenomena cuaca ekstrem mendadak (squall line, downburst, atau hujan deras).\n"
                    "2. Periksa log tegangan catu daya untuk mendeteksi electrical spike/grounding fault pada logger.\n"
                    "3. Jika tidak ada konfirmasi cuaca ekstrem dari radar/satelit, isolasi titik spike sebagai anomali instrumen.\n"
                    "4. Perbaiki grounding dan dokumentasikan temuan di sistem monitoring."
                ),
                sla_target_hours=12,
                escalation_target="Kepala Stasiun & Unit Pemeliharaan Peralatan",
            ),
            SopGuide(
                sop_code="SOP-QC-04",
                violation_type="Persistence Check",
                parameter_scope="ALL",
                title="SOP Penanganan Sensor Macet / Nilai Konstan (Persistence Check)",
                steps_text=(
                    "1. Lakukan inspeksi visual sensor (baling-baling anemometer macet, tipping bucket tersumbat, atau membran RH jenuh).\n"
                    "2. Lakukan restart/reset modul akuisisi pada data logger AWS.\n"
                    "3. Bersihkan komponen mekanik dan uji respons sensor secara manual.\n"
                    "4. Konfirmasi pembacaan dinamis telah pulih sebelum mengubah status menjadi Resolved."
                ),
                sla_target_hours=8,
                escalation_target="Kepala Stasiun & Koordinator Observasi",
            ),
        ]
        db.add_all(sops)

    db.commit()


def seed_baseline_observations(db: Session) -> None:
    """Seed a small, realistic baseline dataset so the dashboard is informative on first launch."""
    if db.query(ObservationRecord).count() > 0:
        return

    now = utcnow().replace(minute=0, second=0, microsecond=0)
    batch = EtlBatch(
        batch_code="ETL-BASELINE-001",
        filename="baseline_synoptic_24h.csv",
        uploaded_by="qc.datin",
        uploaded_at=now - timedelta(hours=6),
        total_rows=20,
        valid_count=17,
        warning_count=2,
        critical_count=1,
        stations_detected="AWS-KMY, AWS-BGR, AWS-TPR",
    )
    db.add(batch)
    db.flush()

    db.add(
        AuditTrail(
            audit_code="AUD-BASE-0001",
            case_id=None,
            case_code=None,
            event_time=now - timedelta(hours=6),
            actor_username="qc.datin",
            actor_name="Rina Kusuma, S.Stat",
            actor_role="staf_qc",
            action_type="ETL_IMPORT",
            previous_status=None,
            new_status="COMPLETED",
            assigned_pic="-",
            notes="Inisialisasi batch baseline historis (20 baris observasi dari 3 stasiun AWS).",
        )
    )

    sample_rows = [
        # Valid baseline records
        (now - timedelta(hours=10), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "temperature", "Suhu Udara (T2M)", "29.4", 29.4, "°C", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=9), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "temperature", "Suhu Udara (T2M)", "30.1", 30.1, "°C", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=8), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "humidity", "Kelembaban Relatif (RH)", "76.0", 76.0, "%", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=7), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "rainfall", "Curah Hujan (RR)", "0.0", 0.0, "mm", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=6), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "pressure", "Tekanan Udara (SLP/QFF)", "1010.2", 1010.2, "hPa", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=5), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "wind_speed", "Kecepatan Angin (WS)", "4.2", 4.2, "m/s", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=10), "AWS-BGR", "Stasiun Klimatologi Bogor", "temperature", "Suhu Udara (T2M)", "25.8", 25.8, "°C", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=9), "AWS-BGR", "Stasiun Klimatologi Bogor", "humidity", "Kelembaban Relatif (RH)", "84.5", 84.5, "%", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=8), "AWS-BGR", "Stasiun Klimatologi Bogor", "rainfall", "Curah Hujan (RR)", "12.4", 12.4, "mm", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=7), "AWS-BGR", "Stasiun Klimatologi Bogor", "pressure", "Tekanan Udara (SLP/QFF)", "1011.5", 1011.5, "hPa", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=6), "AWS-BGR", "Stasiun Klimatologi Bogor", "wind_speed", "Kecepatan Angin (WS)", "2.8", 2.8, "m/s", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=10), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "temperature", "Suhu Udara (T2M)", "30.5", 30.5, "°C", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=9), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "humidity", "Kelembaban Relatif (RH)", "78.0", 78.0, "%", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=8), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "rainfall", "Curah Hujan (RR)", "0.0", 0.0, "mm", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=7), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "pressure", "Tekanan Udara (SLP/QFF)", "1009.8", 1009.8, "hPa", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=6), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "wind_speed", "Kecepatan Angin (WS)", "6.7", 6.7, "m/s", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        (now - timedelta(hours=5), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "temperature", "Suhu Udara (T2M)", "31.0", 31.0, "°C", "Valid", None, "Lolos seluruh validasi WMO-No. 8", True),
        # 3 baseline anomalies (1 resolved, 2 open/in-progress)
        (now - timedelta(hours=8), "AWS-KMY", "Stasiun Meteorologi Kemayoran", "temperature", "Suhu Udara (T2M)", "41.6", 41.6, "°C", "Warning/Suspect", "Range Check", "Nilai 41.6 °C melebihi batas wajar klimatologis (10.0–40.0 °C).", True),
        (now - timedelta(hours=7), "AWS-BGR", "Stasiun Klimatologi Bogor", "humidity", "Kelembaban Relatif (RH)", "14.2", 14.2, "%", "Warning/Suspect", "Range Check", "Nilai 14.2 % berada di bawah batas wajar klimatologis (20.0–100.0 %).", True),
        (now - timedelta(hours=5), "AWS-TPR", "Stasiun Meteorologi Maritim Tanjung Priok", "wind_speed", "Kecepatan Angin (WS)", "NULL", None, "m/s", "Critical/Missing", "Missing Data", "Data kecepatan angin hilang / bernilai NULL pada telemetri AWS.", False),
    ]

    raci_map = {r.station_code: r for r in db.query(RaciRegistry).all()}
    sop_map = {s.violation_type: s for s in db.query(SopGuide).all()}

    case_idx = 1
    for obs_time, scode, sname, pcode, pname, raw_v, num_v, unit, qstatus, qrule, qdetail, svalid in sample_rows:
        rec = ObservationRecord(
            batch_id=batch.id,
            observed_at=obs_time,
            station_code=scode,
            station_name=sname,
            parameter_code=pcode,
            parameter_name=pname,
            raw_value=raw_v,
            numeric_value=num_v,
            unit=unit,
            qc_status=qstatus,
            qc_rule_triggered=qrule,
            qc_detail=qdetail,
            schema_valid=svalid,
            created_at=now - timedelta(hours=6),
        )
        db.add(rec)
        db.flush()

        if qstatus != "Valid":
            raci = raci_map[scode]
            sop = sop_map[qrule]
            is_first = case_idx == 1
            case_code = f"ANM-BASE-{case_idx:04d}"
            sla_hours = raci.sla_hours_critical if qstatus == "Critical/Missing" else raci.sla_hours_warning
            case = AnomalyCase(
                case_code=case_code,
                observation_id=rec.id,
                station_code=scode,
                station_name=sname,
                parameter_code=pcode,
                parameter_name=pname,
                observed_at=obs_time,
                raw_value=raw_v,
                severity=qstatus,
                violation_type=qrule,
                diagnostic_message=qdetail,
                data_owner=raci.accountable_role,
                data_steward=raci.consulted_role,
                responsible_unit=raci.responsible_role,
                assigned_pic_username=raci.assigned_pic_username,
                assigned_pic_name=raci.assigned_pic_name,
                sop_code=sop.sop_code,
                status="Resolved" if is_first else "Open",
                resolution_notes="Sensor radiasi shield dibersihkan; pembacaan kembali normal 32.4 °C." if is_first else None,
                sla_due_at=(now - timedelta(hours=6)) + timedelta(hours=sla_hours),
                is_escalated=False,
                detected_at=now - timedelta(hours=6),
                updated_at=now - timedelta(hours=4) if is_first else now - timedelta(hours=6),
                resolved_at=now - timedelta(hours=4) if is_first else None,
            )
            db.add(case)
            db.flush()

            db.add(
                AuditTrail(
                    audit_code=f"AUD-BASE-C{case_idx:03d}A",
                    case_id=case.id,
                    case_code=case_code,
                    event_time=now - timedelta(hours=6),
                    actor_username="system.qc",
                    actor_name="Mesin QC Otomatis (WMO-No. 8)",
                    actor_role="system",
                    action_type="DETECTED",
                    previous_status=None,
                    new_status="Open",
                    assigned_pic=raci.assigned_pic_name,
                    notes=f"Anomali {qrule} terdeteksi pada {sname} ({pname}={raw_v}). Otomatis ditugaskan ke {raci.assigned_pic_name}.",
                )
            )
            if is_first:
                db.add(
                    AuditTrail(
                        audit_code=f"AUD-BASE-C{case_idx:03d}B",
                        case_id=case.id,
                        case_code=case_code,
                        event_time=now - timedelta(hours=4),
                        actor_username=raci.assigned_pic_username,
                        actor_name=raci.assigned_pic_name,
                        actor_role="teknisi",
                        action_type="STATUS_CHANGE",
                        previous_status="Open",
                        new_status="Resolved",
                        assigned_pic=raci.assigned_pic_name,
                        notes="Sensor radiasi shield dibersihkan; pembacaan kembali normal 32.4 °C.",
                    )
                )
            case_idx += 1

    db.commit()
