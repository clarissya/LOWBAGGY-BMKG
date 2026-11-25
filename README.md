# Platform Web Monitoring Kualitas Data & Tata Kelola Observasi BMKG

Sistem terpadu (*one-door dashboard*) yang disesuaikan dengan alur operasional nyata BMKG (**Observer → Datin → Forecaster**) serta rancangan tata kelola IT (*Data Dictionary*, matriks *RACI*, *Usulan SOP*, dan *Audit Trail* permanen) berstandar **WMO-No. 8**.

## 4 Peran Pengguna (Password demo: `bmkg123`)

1. **`datin.qc` — Bidang Datin / Staf QC (Data & Informasi):** Mengunggah file CSV/Excel mentah (interval 10-menit maupun 1-jam), memantau dashboard, verifikasi penyelesaian (`Verified`), dan simulasi eskalasi SLA.
2. **`observer.tprk` & `observer.tuban` — Observer / Teknisi AWS:** Menerima penugasan anomali per stasiun, melihat rancangan SOP, melakukan kalibrasi/*backfill*, dan mengubah status ke `Resolved`.
3. **`forecaster` — Forecaster / Prakiraan Maritim:** Memantau grafik tendensi 24 jam / 3 hari terakhir beserta penanda *suspect*, dan mengembalikan temuan data aneh ke Bidang Datin (*Return to Datin*).
4. **`manajemen` — Manajemen / Kepala UPT:** Memantau ringkasan KPI kualitas data, kepatuhan usulan SOP/SLA, dan log jejak audit (*read-only*).

## Penyesuaian Utama dari Hasil Wawancara BMKG

- **Alur 3 Divisi Operasional:** Observer (pengamatan & perbaikan alat) → Datin (arsip 10-menit, QC, feed 1-jam pusat) → Forecaster (cek tendensi & layanan).
- **Grafik Tendensi Real-Time (24 Jam / 72 Jam):** Menampilkan deret waktu dengan sorotan titik merah/kuning untuk mendeteksi lonjakan (seperti suhu `25°C → 35°C` atau tekanan `1010 → 1020 mb`).
- **Standar Satuan Angin Maritim (`knots`):** Data kecepatan angin dalam `m/s` dari AWS otomatis dikonversi (`× 1.94384`) menjadi **`knots`** sesuai standar layanan maritim BMKG.
- **Resolusi 10-Menit vs 1-Jam:** Mesin ETL mendeteksi interval data secara otomatis dan menggantikan koreksi manual bulanan dengan *auto-flagging* seketika.
- **Blueprint Tata Kelola & Usulan SOP:** Karena sebelumnya belum ada SOP khusus QC data di Datin, modul Tata Kelola memodelkan rancangan SOP, matriks RACI, dan *Audit Trail* *append-only*.

## Menjalankan Aplikasi

```powershell
c:\CAPSTONE\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

Buka browser ke: `http://127.0.0.1:8000`

## Pengujian Otomatis

```powershell
c:\CAPSTONE\.venv\Scripts\python.exe -m pytest -v c:\CAPSTONE\tests\test_end_to_end.py
```
