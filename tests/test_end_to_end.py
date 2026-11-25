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


def test_end_to_end_bmkg_workflow(client: TestClient):
    # Reset demo baseline first as Staf QC
    qc_headers = _auth_header(client, "qc.datin")
    tek_headers = _auth_header(client, "teknisi.obs")
    mgr_headers = _auth_header(client, "manajemen")

    r_reset = client.post("/api/etl/reset-demo", headers=qc_headers)
    assert r_reset.status_code == 200

    # Baseline dashboard snapshot
    dash_before = client.get("/api/dashboard", headers=qc_headers).json()
    assert dash_before["kpis"]["total_observations"] == 20

    # RBAC checks: Teknisi & Manajemen cannot upload ETL
    sample_a = (SAMPLE_DIR / "stasiun_kemayoran_format_a.csv").read_bytes()
    r_forbidden = client.post(
        "/api/etl/upload",
        headers=tek_headers,
        files={"files": ("stasiun_kemayoran_format_a.csv", sample_a, "text/csv")},
    )
    assert r_forbidden.status_code == 403

    # Step 1 & 2: Staf QC uploads 3 heterogeneous station CSV files
    sample_files = [
        ("files", ("stasiun_kemayoran_format_a.csv", (SAMPLE_DIR / "stasiun_kemayoran_format_a.csv").read_bytes(), "text/csv")),
        ("files", ("stasiun_bogor_format_b.csv", (SAMPLE_DIR / "stasiun_bogor_format_b.csv").read_bytes(), "text/csv")),
        ("files", ("stasiun_tanjung_priok_format_c.csv", (SAMPLE_DIR / "stasiun_tanjung_priok_format_c.csv").read_bytes(), "text/csv")),
    ]
    r_upload = client.post("/api/etl/upload", headers=qc_headers, files=sample_files)
    assert r_upload.status_code == 200, r_upload.text
    batches = r_upload.json()["batches"]
    assert len(batches) == 3

    total_new_anomalies = sum(b["new_anomaly_cases"] for b in batches)
    assert total_new_anomalies >= 12  # Expect ~15-17 anomalies across 3 stations

    # Also test Excel (.xlsx) upload
    xlsx_buf = io.BytesIO()
    df_xlsx = pd.DataFrame(
        [
            {"waktu_obs": "2026-11-25 12:00:00", "stasiun": "AWS-KMY", "temp_c": 30.0, "rh_pct": 70.0},
        ]
    )
    df_xlsx.to_excel(xlsx_buf, index=False, engine="openpyxl")
    r_xlsx = client.post(
        "/api/etl/upload",
        headers=qc_headers,
        files={"files": ("test_kemayoran.xlsx", xlsx_buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r_xlsx.status_code == 200, r_xlsx.text
    assert r_xlsx.json()["batches"][0]["total_rows"] == 2

    # Step 3: Dashboard updates dynamically with new observations & anomalies
    dash_after = client.get("/api/dashboard", headers=mgr_headers).json()
    assert dash_after["kpis"]["total_observations"] > dash_before["kpis"]["total_observations"]
    assert dash_after["kpis"]["total_anomalies"] > dash_before["kpis"]["total_anomalies"]
    assert len(dash_after["by_station"]) == 3
    assert len(dash_after["by_parameter"]) >= 5

    # Test dashboard filter by station
    dash_kmy = client.get("/api/dashboard?station_code=AWS-KMY", headers=mgr_headers).json()
    assert len(dash_kmy["by_station"]) == 1
    assert dash_kmy["by_station"][0]["station_code"] == "AWS-KMY"

    # Step 4: Staf QC inspects Critical/Missing anomaly detail (RACI + SOP)
    anoms = client.get("/api/anomalies?severity=Critical/Missing&status=Open", headers=qc_headers).json()
    assert len(anoms) > 0
    target_case = next((a for a in anoms if a["station_code"] == "AWS-KMY"), anoms[0])
    detail = client.get(f"/api/anomalies/{target_case['id']}", headers=qc_headers).json()
    assert "Teknisi" in detail["raci"]["responsible"]
    assert "Data Owner" in detail["raci"]["accountable"]
    assert len(detail["sop"]["steps"]) >= 3

    # RBAC: Manajemen cannot update case status
    r_mgr_patch = client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=mgr_headers,
        json={"status": "Resolved", "resolution_notes": "Mencoba ubah"},
    )
    assert r_mgr_patch.status_code == 403

    # Step 5: Teknisi resolves the case with repair notes
    r_resolve = client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=tek_headers,
        json={"status": "Resolved", "resolution_notes": "Sensor AWS dikalibrasi ulang dan logger di-restart."},
    )
    assert r_resolve.status_code == 200, r_resolve.text
    assert r_resolve.json()["status"] == "Resolved"

    # Staf QC verifies resolution
    r_verify = client.patch(
        f"/api/anomalies/{target_case['id']}/status",
        headers=qc_headers,
        json={"status": "Verified", "resolution_notes": "Data observasi pasca-perbaikan telah diverifikasi valid."},
    )
    assert r_verify.status_code == 200
    assert r_verify.json()["status"] == "Verified"

    # Escalation simulation on another Open case
    open_cases = client.get("/api/anomalies?status=Open", headers=qc_headers).json()
    assert len(open_cases) > 0
    esc_case = open_cases[0]
    r_esc = client.post(
        f"/api/anomalies/{esc_case['id']}/escalate",
        headers=qc_headers,
        json={"reason": "Melewati batas SLA 4 jam untuk Critical/Missing."},
    )
    assert r_esc.status_code == 200
    assert r_esc.json()["is_escalated"] is True

    # Step 6: Audit trail contains all actions and cannot be deleted
    audit_logs = client.get(f"/api/governance/audit-trail?case_code={target_case['case_code']}", headers=mgr_headers).json()
    actions = {log["action_type"] for log in audit_logs}
    assert {"DETECTED", "STATUS_CHANGE", "VERIFIED"}.issubset(actions)

    # Confirm immutability (no DELETE endpoint)
    r_del = client.delete("/api/governance/audit-trail", headers=qc_headers)
    assert r_del.status_code == 405

    # Reset demo data back to clean baseline after test
    client.post("/api/etl/reset-demo", headers=qc_headers)
