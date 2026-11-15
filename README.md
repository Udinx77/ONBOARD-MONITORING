# FMSONB - Fleet Monitoring System (On-Board)

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat&logo=python&logoColor=white)
![Backend](https://img.shields.io/badge/Backend-Flask-000000?style=flat&logo=flask&logoColor=white)
![Database](https://img.shields.io/badge/Database-SQLite3-003B57?style=flat&logo=sqlite&logoColor=white)
![Protocol](https://img.shields.io/badge/Protocol-ICMP_%7C_SNMP_%7C_REST_API-EA580C?style=flat)
![Integration](https://img.shields.io/badge/Integration-Cat_MineStar-F59E0B?style=flat)

**FMSONB** adalah sistem pemantauan berbasis Python (**Flask** & **SQLite**) yang dirancang khusus untuk mengawasi status konektivitas jaringan, tingkat ketersediaan (*availability*), metrik sinyal GPS, serta integrasi antarmuka sistem **Caterpillar MineStar** pada unit *on-board* alat berat dan kendaraan operasional tambang secara *real-time*.

---

## 📑 Daftar Isi

- [Dokumentasi Lanjutan](#-dokumentasi-lanjutan)
- [Fitur Utama](#-fitur-utama)
- [Arsitektur Sistem](#-arsitektur-sistem)
- [Struktur Proyek](#-struktur-proyek)
- [Prasyarat Sistem](#-prasyarat-sistem)
- [Panduan Instalasi](#-panduan-instalasi)
- [Panduan Penggunaan](#-panduan-penggunaan)
- [Formulasi Perhitungan Availability](#-formulasi-perhitungan-availability)
- [Skema Basis Data & Pemetaan Unit](#-skema-basis-data--pemetaan-unit)
- [Konfigurasi Sistem](#-konfigurasi-sistem)
- [Lisensi & Pemeliharaan](#-lisensi--pemeliharaan)

---

## 📚 Dokumentasi Lanjutan

- [Dokumentasi Teknis & Skema Database](./dokumentasi_teknis_skema_database.md) – Penjelasan detail struktur modul, arsitektur data, dan skema tabel SQLite (`monitoring.db`).
- [Spesifikasi API & Integrasi MineStar](./spesifikasi_api_integrasi_minestar.md) – Detail *endpoint* REST API (`app.py`), format *payload* JSON, dan alat diagnosa antarmuka Caterpillar MineStar.

---

## 📌 Fitur Utama

- **Monitoring Jaringan Real-Time:** *Service* latar belakang (`collect_ping.py`) melakukan *polling* ICMP ping secara berkala untuk memantau latensi, *packet loss*, dan status *online/offline* tiap unit.
- **Ekstraksi Metrik GPS:** Mengumpulkan data posisi koordinat, kecepatan, dan kualitas sinyal GPS dari perangkat *on-board* (`gps_metric.py`).
- **Integrasi Cat MineStar:** Modul pembaca antarmuka data MineStar (`minestar_source.py`, `minestar_sources.py`) serta utilitas uji diagnostik antarmuka (`diagnose_minestar_interfaces.py`).
- **Pemetaan & Caching Unit:** Pengolah otomatis data pemetaan IP & OID SNMP dari berkas Excel (`dataoidip.xlsx`) yang disimpan dalam format *cache* JSON lokal (`machine_map_cache.json`).
- **Perhitungan Availability & Laporan:** Algoritma kalkulasi ketersediaan perangkat (*uptime* vs *downtime*) harian, mingguan, dan bulanan (`availability.py`, `availability_report.py`).
- **Dashboard Web & REST API:** *Dashboard* visual berbasis Flask (`app.py`) untuk pemantauan operasional serta penyediaan *endpoint* JSON REST API.
- **Manajemen Database & Cadangan:** Pengelolaan log berbasis SQLite (`monitoring.db`) dilengkapi skrip pembuatan cadangan otomatis (`backup_db.py`).

---

## 🏗️ Arsitektur Sistem

```text
┌──────────────────────┐      ┌────────────────────────────────────────┐
│    dataoidip.xlsx    │─────►│ machine_map.py -> machine_map_cache.json│
│ (Master IP & OID Unit)│      └───────────────────┬────────────────────┘
└──────────────────────┘                          │
                                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      Background Collectors & Services                 │
│                                                                       │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  │
│  │  collect_ping.py  │  │   gps_metric.py   │  │ minestar_source.py│  │
│  │ (ICMP Ping Poll)  │  │  (GPS Telemetry)  │  │  (Cat MineStar)   │  │
│  └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘  │
└────────────┼──────────────────────┼──────────────────────┼────────────┘
             └──────────────────────┼──────────────────────┘
                                    ▼
                     ┌─────────────────────────────┐      ┌──────────────┐
                     │ SQLite DB (monitoring.db)   │─────►│ backup_db.py │
                     └──────────────┬──────────────┘      └──────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
   ┌──────────────────────────────┐    ┌──────────────────────────────┐
   │  availability.py & Report    │    │   app.py (Flask Server)      │
   │  (Kalkulasi Uptime/Downtime) │───►│   • Web Dashboard (:5000)    │
   └──────────────────────────────┘    │   • JSON REST API            │
                                       └──────────────────────────────┘
```

---

## 📁 Struktur Proyek

```text
ONBOARD-MONITORING/
│
├── app.py                          # Server web Flask dan penyedia REST API
├── config.py                       # Konfigurasi parameter & konstanta sistem
├── db.py                           # Modul manajemen skema & query SQLite
├── backup_db.py                    # Skrip backup otomatis basis data
│
├── collect_ping.py                 # Service pemantauan konektivitas (ICMP ping)
├── gps_metric.py                   # Service ekstraksi & pemrosesan metrik GPS
│
├── machine_map.py                  # Pengolah pemetaan IP/OID unit dari berkas Excel
├── dataoidip.xlsx                  # Sumber data Excel untuk IP & OID perangkat
│
├── availability.py                 # Algoritma perhitungan ketersediaan unit
├── availability_report.py          # Generator laporan ketersediaan perangkat
│
├── minestar_source.py              # Modul integrasi Caterpillar MineStar
├── minestar_sources.py             # Konfigurasi sumber data MineStar
├── diagnose_minestar_interfaces.py # Utilitas tes koneksi & validasi antarmuka MineStar
│
├── monitoring.db                   # (Runtime) File basis data utama SQLite
└── machine_map_cache.json          # (Runtime) Berkas cache lokal pemetaan unit
```

---

## 🛠️ Prasyarat Sistem

Sebelum menjalankan aplikasi, pastikan sistem memenuhi spesifikasi berikut:

- **Sistem Operasi:** Linux (Ubuntu 20.04+ / Debian 11+ direkomendasikan) atau Windows 10/11 / Windows Server
- **Python:** Versi 3.8 atau lebih baru
- **Database:** SQLite 3.x
- **Library Python Utama:**
  - `Flask` (Web framework & REST API)
  - `pandas` & `openpyxl` (Pengolahan pemetaan data Excel)
  - `requests` (HTTP requests)

---

## 🚀 Panduan Instalasi

### 1. Clone Repositori
```bash
git clone [https://github.com/Udinx77/ONBOARD-MONITORING.git](https://github.com/Udinx77/ONBOARD-MONITORING.git)
cd ONBOARD-MONITORING
```

### 2. Buat & Aktifkan Virtual Environment
```bash
# Membuat virtual environment
python -m venv venv

# Aktivasi pada Linux / macOS:
source venv/bin/activate

# Aktivasi pada Windows (Command Prompt):
venv\Scripts\activate.bat

# Aktivasi pada Windows (PowerShell):
venv\Scripts\Activate.ps1
```

### 3. Install Dependensi
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
*(Catatan: Jika berkas `requirements.txt` belum tersedia, instal dependensi secara manual melalui `pip install Flask pandas openpyxl requests`)*

### 4. Persiapan Berkas Pemetaan
Pastikan berkas `dataoidip.xlsx` berada di direktori utama proyek. Berkas ini memuat daftar unit alat berat, alamat IP, dan OID SNMP perangkat *on-board*. Berkas `machine_map_cache.json` akan dibuat secara otomatis saat sistem pertama kali dijalankan.

---

## 💻 Panduan Penggunaan

### 1. Menjalankan Dashboard Web & REST API
Jalankan aplikasi Flask untuk membuka antarmuka pemantauan:
```bash
python app.py
```
Secara bawaan, *dashboard* dapat diakses melalui browser pada alamat `http://localhost:5000`.

### 2. Menjalankan Service Monitoring (Background Tasks)
Jalankan *service* pengumpul data secara terpisah di latar belakang. Pada lingkungan produksi, disarankan menggunakan *process manager* seperti **Systemd**, **Supervisor**, atau **Windows Task Scheduler**.

- **Service Monitoring Jaringan (ICMP Ping):**
  ```bash
  python collect_ping.py
  ```
- **Service Monitoring Sinyal GPS:**
  ```bash
  python gps_metric.py
  ```

### 3. Diagnosa Antarmuka & Pemeliharaan
- **Uji Koneksi & Validasi Antarmuka Cat MineStar:**
  ```bash
  python diagnose_minestar_interfaces.py
  ```
- **Generate Laporan Availability:**
  ```bash
  python availability_report.py
  ```
- **Backup Database Manual (`monitoring.db`):**
  ```bash
  python backup_db.py
  ```

---

## 📊 Formulasi Perhitungan Availability

Tingkat ketersediaan koneksi perangkat *on-board* dihitung menggunakan persentase rasio antara jumlah respons ping yang diterima dengan total permintaan ping yang dijadwalkan dalam rentang waktu tertentu.

Persamaan matematis perhitungan ketersediaan ($A$):

$$A = \left( \frac{N_{\text{success}}}{N_{\text{total}}} \right) \times 100\%$$

Keterangan:
- $A$: Persentase *Availability* (%)
- $N_{\text{success}}$: Jumlah respons ping sukses (unit berstatus *online*)
- $N_{\text{total}}$: Total akumulasi percobaan ping yang dijadwalkan dalam periode pengamatan

---

## 🗄️ Skema Basis Data & Pemetaan Unit

### Ringkasan Tabel `monitoring.db`
1. **`ping_logs`**: Menyimpan *timestamp*, IP unit, latensi (`ms`), dan status koneksi (`1` = Online, `0` = Offline).
2. **`gps_metrics`**: Menyimpan *timestamp*, ID unit, koordinat *latitude/longitude*, kecepatan, serta indikator kualitas sinyal GPS.
3. **`availability_summary`**: Rekapitulasi persentase *uptime*, *downtime*, dan total durasi terhubung harian/bulanan per unit.

### Alur Pemetaan Data Unit
```text
[dataoidip.xlsx] ──► [machine_map.py] ──► [machine_map_cache.json] ──► [Service Monitoring]
```

---

## ⚙️ Konfigurasi Sistem

Pengaturan utama aplikasi tersimpan dalam berkas `config.py`. Sesuaikan parameter berikut sesuai lingkungan jaringan operasional:

| Parameter | Deskripsi |
|---|---|
| `PING_INTERVAL` | Interval siklus *polling* pengujian konektivitas jaringan (dalam detik) |
| `DATABASE_PATH` | Lokasi penyimpanan berkas basis data SQLite (`monitoring.db`) |
| `BACKUP_DIR` | Direktori tujuan penyimpanan berkas cadangan (*backup*) basis data |
| `MINESTAR_API_URL` | URL *endpoint* antarmuka sistem Caterpillar MineStar |

---

## 🛡️ Lisensi & Pemeliharaan

Hak cipta dan pemeliharaan proyek ini berada di bawah pengawasan tim **IT Operations & Fleet Management System**. Untuk bantuan teknis atau pelaporan kendala sistem, silakan hubungi administrator jaringan/FMS terkait.
