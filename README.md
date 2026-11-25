# Platform Web Monitoring Kualitas Data & Tata Kelola Observasi BMKG

Sistem terpadu (*one-door dashboard*) untuk pemantauan kualitas data observasi AWS/sinoptik berdasarkan standar **WMO-No. 8**, validasi skema otomatis melalui modul ETL, pelacakan anomali berbasis matriks **RACI** & panduan **SOP**, serta **Audit Trail** permanen (*append-only*).

## Fitur Utama

1. **Login & Hak Akses Berbasis Peran (RBAC):**
   - `qc.datin` / `bmkg123` (**Staf QC / Datin**): Unggah data mentah CSV/Excel, pantau dashboard, verifikasi penyelesaian kasus, kelola simulasi eskalasi.
   - `teknisi.obs` & `teknisi.bogor` / `bmkg123` (**Teknisi / Unit Observasi**): Menerima notifikasi kasus anomali, melihat panduan SOP, memperbarui status perbaikan ke `Resolved`.
   - `manajemen` / `bmkg123` (**Manajemen**): Memantau ringkasan agregat kualitas data dan kepatuhan SLA/SOP lintas stasiun.
2. **Dashboard Ringkasan Kualitas Data:**
   - KPI *Completeness %*, *Validity %*, Total Anomali, Kasus Belum Tertangani, dan Kepatuhan SOP/SLA.
   - Grafik interaktif per Stasiun AWS & per Parameter Cuaca + Distribusi pelanggaran WMO-No. 8.
   - Filter global berdasarkan rentang tanggal, stasiun, dan parameter.
3. **Modul ETL & Mesin QC Otomatis (WMO-No. 8):**
   - Menyerap file CSV/Excel dengan format heterogen (nama kolom alias, pemisah `,`/`;`, format tanggal berbeda, desimal koma, konversi `knot` ke `m/s`).
   - Menjalankan pengecekan: **Missing Data**, **Gross Range Check**, **Temporal Step Check**, dan **Persistence Check** (dengan pengecualian hujan `0.0 mm`).
4. **Monitoring Anomali & Modal Tindak Lanjut:**
   - Tabel indikator warna merah (`Critical/Missing`) dan kuning (`Warning/Suspect`).
   - Pop-up detail berisi diagnosa error, penanggung jawab otomatis dari tabel RACI (`R/A/C/I`), langkah SOP, form update status, serta tombol **Simulasi Eskalasi SLA**.
5. **Tata Kelola & Jejak Audit:**
   - Log **Audit Trail** kronologis yang bersifat *append-only* (tidak dapat dihapus).
   - **Data Dictionary** standar WMO-No. 8, **RACI Registry**, dan katalog **SOP**.

## Menjalankan Aplikasi

```powershell
# Aktifkan virtual environment atau gunakan python di .venv
c:\CAPSTONE\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
```

Buka browser ke: `http://127.0.0.1:8000`

### Menggunakan PostgreSQL (Opsional)

Secara default aplikasi menggunakan SQLite (`bmkg_qc.db`) agar langsung berjalan tanpa konfigurasi tambahan. Untuk menyambungkan ke PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql+psycopg2://postgres:password@localhost:5432/bmkg_qc"
c:\CAPSTONE\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

## Menjalankan Pengujian Otomatis

```powershell
c:\CAPSTONE\.venv\Scripts\pytest.exe -v
```
