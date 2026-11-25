import io
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _auth_header(client: TestClient, username: str, password: str = "bmkg123") -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_end_to_end_bmkg_interview_workflow(client: TestClient):
    datin_headers = _auth_header(client, "datin.qc")
    obs_headers = _auth_header(client, "observer.tprk")
    fc_headers = _auth_header(client, "forecaster")
    mgr_headers = _auth_header(client, "manajemen")

    r_reset = client.post("/api/etl/reset-demo", headers=datin_headers)
    assert r_reset.status_code == 200

    # Baseline 24h maritime dataset: 24h * 3 stations * 3 params = 216 observations
    dash_before = client.get("/api/dashboard", headers=datin_headers).json()
    assert dash_before["kpis"]["total_observations"] == 216

    # Check 24h and 72h tendency endpoint for Forecaster
    ts_24 = client.get("/api/dashboard/timeseries?station_code=AWS-TPRK&parameter_code=temperature&window_hours=24", headers=fc_headers)
    assert ts_24.status_code == 200
    assert ts_24.json()["unit"] == "°C"
    assert len(ts_24.json()["points"]) == 24

    # RBAC checks: Observer, Forecaster & Manajemen cannot upload ETL
    sample_a = (SAMPLE_DIR / "aws_tanjung_perak_10menit.csv").read_bytes()
    for forbidden_hdr in (obs_headers, fc_headers, mgr_headers):
        r_forb = client.post(
            "/api/etl/upload",
            headers=forbidden_hdr,
            files={"files": ("aws_tanjung_perak_10menit.csv", sample_a, "text/csv")},
        )
        assert r_forb.status_code == 403

    # Step 1 & 2: Datin uploads 3 heterogeneous station CSV files (10-minute + 1-hour, m/s -> knots)
    sample_files = [
        ("files", ("aws_tanjung_perak_10menit.csv", (SAMPLE_DIR / "aws_tanjung_perak_10menit.csv").read_bytes(), "text/csv")),
        ("files", ("aws_tuban_format_b.csv", (SAMPLE_DIR / "aws_tuban_format_b.csv").read_bytes(), "text/csv")),
        ("files", ("aws_lamongan_format_c.csv", (SAMPLE_DIR / "aws_lamongan_format_c.csv").read_bytes(), "text/csv")),
    ]
    r_upload = client.post("/api/etl/upload", headers=datin_headers, files=sample_files)
    assert r_upload.status_code == 200, r_upload.text
    batches = r_upload.json()["batches"]
    assert len(batches) == 3

    # Verify 10-minute vs 1-hour interval detection
    intervals = {b["filename"]: b["interval_type"] for b in batches}
    assert intervals["aws_tanjung_perak_10menit.csv"] == "10m"
    assert intervals["aws_tuban_format_b.csv"] == "1h"

    # Verify wind speed m/s -> knots conversion in AWS-TBN (5.2 m/s -> ~10.11 knots)
    ts_wind = client.get("/api/dashboard/timeseries?station_code=AWS-TBN&parameter_code=wind_speed&window_hours=24", headers=fc_headers).json()
    assert ts_wind["unit"] == "knots"
    converted_pts = [p for p in ts_wind["points"] if p["raw_value"] == "5,2"]
    assert converted_pts and 10.0 <= converted_pts[0]["numeric_value"] <= 10.2

    # Excel upload verification
    xlsx_buf = io.BytesIO()
    df_xlsx = pd.DataFrame(
        [{"waktu_obs": "2026-11-25 12:00:00", "stasiun": "AWS-TPRK", "temp_c": 30.2, "wind_ms": 5.0}]
    )
    df_xlsx.to_excel(xlsx_buf, index=False, engine="openpyxl")
    r_xlsx = client.post(
        "/api/etl/upload",
        headers=datin_headers,
        files={"files": ("test_tprk.xlsx", xlsx_buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_xlsx.status_code == 200, r_xlsx.text
    assert r_xlsx.json()["batches"][0]["total_rows"] == 2

    # Step 3: Dashboard updates dynamically & supports interval filter
    dash_after = client.get("/api/dashboard", headers=mgr_headers).json()
    assert dash_after["kpis"]["total_observations"] > dash_before["kpis"]["total_observations"]
    assert dash_after["kpis"]["total_anomalies"] > dash_before["kpis"]["total_anomalies"]
    assert len(dash_after["by_station"]) == 3

    dash_10m = client.get("/api/dashboard?interval_type=10m", headers=mgr_headers).json()
    assert dash_10m["kpis"]["total_observations"] == 35  # 7 rows * 5 params in aws_tanjung_perak_10menit.csv

    # Step 4: Inspect anomaly detail (RACI, Blueprint SOP, nearby tendency context)
    anoms = client.get("/api/anomalies?severity=Critical/Missing&status=Open", headers=datin_headers).json()
    assert len(anoms) > 0
    target_case = next((a for a in anoms if a["station_code"] == "AWS-TPRK"), anoms[0])
    detail = client.get(f"/api/anomalies/{target_case['id']}", headers=fc_headers).json()
    assert "Observer" in detail["raci"]["responsible"]
    assert "Data Owner" in detail["raci"]["accountable"]
    assert len(detail["sop"]["steps"]) >= 3
    assert len(detail["nearby_timeseries"]) >= 2

    # RBAC: Manajemen & Forecaster cannot directly set Resolved status
    for ro_hdr in (mgr_headers, fc_headers):
        r_ro = client.patch(
            f"/api/anomalies/{target_case['id']}/status",
            headers=ro_hdr,
            json={"status": "Resolved", "resolution_notes": "Mencoba ubah langsung"},
        )
        assert r_ro.status_code == 403

    # Step 5A: Observer resolves the case
    r_resolve = client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=obs_headers,
        json={"status": "Resolved", "resolution_notes": "Backfill log 10-menit AWS Tanjung Perak selesai dilakukan."},
    )
    assert r_resolve.status_code == 200
    assert r_resolve.json()["status"] == "Resolved"

    # Step 5B: Forecaster finds discrepancy & returns case to Datin
    r_ret = client.post(
        f"/api/anomalies/{target_case['id']}/return-to-datin",
        headers=fc_headers,
        json={"notes": "Nilai suhu masih belum sinkron dengan radar maritim, mohon cek ulang Datin."},
    )
    assert r_ret.status_code == 200
    assert r_ret.json()["status"] == "Open"

    # Step 5C: Observer fixes again & Datin verifies
    client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=obs_headers,
        json={"status": "Resolved", "resolution_notes": "Sensor dikalibrasi ulang di lapangan."},
    )
    r_verify = client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=datin_headers,
        json={"status": "Verified", "resolution_notes": "Data terverifikasi valid untuk layanan Forecaster."},
    )
    assert r_verify.status_code == 200
    assert r_verify.json()["status"] == "Verified"

    # Escalation simulation on another Open case
    open_cases = client.get("/api/anomalies?status=Open", headers=datin_headers).json()
    assert len(open_cases) > 0
    r_esc = client.post(
        f"/api/anomalies/{open_cases[0]['id']}/escalate",
        headers=datin_headers,
        json={"reason": "Melewati batas SLA 4 jam."},
    )
    assert r_esc.status_code == 200
    assert r_esc.json()["is_escalated"] is True

    # Step 6: Immutable Audit Trail captures full lifecycle
    audit_logs = client.get(f"/api/governance/audit-trail?case_code={target_case['case_code']}", headers=mgr_headers).json()
    actions = {log["action_type"] for log in audit_logs}
    assert {"DETECTED", "STATUS_CHANGE", "RETURNED_TO_DATIN", "VERIFIED"}.issubset(actions)
    assert client.delete("/api/governance/audit-trail", headers=datin_headers).status_code == 405

    # Reset back to clean 24h baseline
    client.post("/api/etl/reset-demo", headers=datin_headers)
