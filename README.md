# Energy Forecast DK

Predict electricity consumption (MW) in Denmark using hourly time-series data from the Energi Data Service and weather data from the Open-Meteo API. The goal is to help grid operators and energy providers prevent energy waste and blackouts.

## Architecture

```
energy-forecast-dk/
├── src/                          # Memenuhi rubrik tugas: src/ingest_data.py & src/preprocess.py
│   ├── ingest_data.py            # Wrapper ingestion (Requests) — timestamp non-destruktif
│   ├── preprocess.py             # Wrapper preprocessing — missing-value handling
│   ├── data/                     # Folder src/data (rubrik Persiapan Lingkungan)
│   │   └── .gitkeep
│   └── energy_forecast/          # Python package (installable via pip install -e .)
│       ├── config.py             # Parameters: country, coordinates, API URLs, paths, MinIO/MLflow config
│       ├── data/                 # Ingestion modular & feature engineering & MinIO upload
│       │   ├── fetch_energy_dk.py  # -> dipanggil oleh src/ingest_data.py (timestamped)
│       │   ├── fetch_weather.py    # -> dipanggil oleh src/ingest_data.py (timestamped)
│       │   └── merge_data.py       # -> dipanggil oleh src/preprocess.py (clean_missing_values)
│       ├── models/               # Training with MLflow tracking
│       │   ├── train.py             # Three MLflow runs + best-model selection
│       │   ├── train_baseline.py
│       │   └── train_deep_learning.py
│       ├── predict/              # Inference
│       │   └── predict_future.py
│       ├── monitoring/           # Evaluation, drift detection & retraining trigger
│       │   ├── evaluate_model.py
│       │   ├── detect_drift.py
│       │   └── check_trigger.py
│       ├── serving/              # FastAPI model serving
│       │   └── serve_model.py
│       └── orchestration/        # Pipeline runner
│           ├── daily_pipeline.py
│           └── prefect_flow.py
├── dags/                         # Apache Airflow DAGs
│   └── energy_forecast_dag.py
├── monitoring/                   # Prometheus & Grafana configuration
│   ├── prometheus.yml
│   └── grafana/
├── data/
│   ├── raw/                      # Raw data: consumption.csv + timestamped + sample_*.csv (untuk tugas)
│   │   ├── consumption.csv            # latest snapshot (overwritten tiap run, tapi arsip timestamp dipertahankan)
│   │   ├── consumption_YYYYMMDD_HHMMSS.csv  # arsip non-destruktif
│   │   ├── weather.csv / weather_*.csv
│   │   ├── sample_consumption.csv   # 100 baris sampel lokal; pointer .dvc dilacak Git
│   │   └── sample_weather.csv
│   └── processed/                # Merged feature table
│       ├── merged_data.csv
│       └── sample_merged_data.csv
├── models/                       # Trained models (git-ignored)
├── logs/                         # Monitoring & drift logs (git-ignored)
├── docs/
│   └── README.md                 # Detailed pipeline & usage documentation
├── Dockerfile                    # API container image
├── docker-compose.yml            # Full stack: API, MLflow, Prometheus, Grafana
├── pyproject.toml
├── .gitignore
└── README.md
```

## Data Sources

| Source | Data | API Key |
|--------|------|---------|
| [Energi Data Service](https://www.energidataservice.dk/) | Hourly electricity consumption (MW) | None |
| [Open-Meteo](https://open-meteo.com/) | Weather: temperature, humidity, wind | None |

## Prerequisites

- Python 3.10+
- [Git](https://git-scm.com/)
- Internet access (to reach the APIs)
- Docker & Docker Compose (for full MLOps stack)
- MinIO on port 9000 for object storage. It is included in `docker-compose.yml`; for local non-Docker runs, start it manually or set `MINIO_ENDPOINT`.
- Apache Airflow (for DAG-based orchestration)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/VeryFach/energy-forecast-dk.git
cd energy-forecast-dk
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate the environment:

- **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Linux/macOS:**
  ```bash
  source .venv/bin/activate
  ```

### 3. Install dependencies

```bash
pip install -e .
```

Optional extras:

```bash
# Deep learning (TensorFlow)
pip install -e ".[deep-learning]"

# FastAPI serving
pip install -e ".[serving]"

# Apache Airflow
pip install -e ".[airflow]"

# All optional dependencies
pip install -e ".[all]"
```

## [LK-4] Implementasi Penarikan Data (Data Ingestion) Dinamis dan Automasi Prapemrosesan

> **Luaran Wajib:** `src/ingest_data.py`, `src/preprocess.py`, `data/raw/sample_*.csv`, `src/data/`.

### Metode Pengerjaan Aktivitas

#### 1. Persiapan Lingkungan
Pastikan folder `src/data` dan `data/raw` tersedia sudah disiapkan via `src/data/.gitkeep` dan `data/raw/.gitkeep`. Di Codespaces/Linux:
```bash
ls -R src/data data/raw
# src/data/.gitkeep ada, data/raw/ terbuat otomatis oleh skrip (RAW_DIR.mkdir)
```

#### 2. Implementasi Penarikan Data Dinamis
Menggunakan `requests` (sesuai opsi BeautifulSoup/Selenium/Requests) untuk menarik data dinamis dari:
- **Energi Data Service** (`https://api.energidataservice.dk/dataset/GenerationProdTypeExchange`, `GrossCon` → `ConsumptionMW`) tanpa API key
- **Open-Meteo Archive** (`https://archive-api.open-meteo.com/v1/archive`) untuk cuaca Copenhagen

**Cara menjalankan di GitHub Codespaces / lokal:**
```bash
# Opsi A — wrapper tugas:
python src/ingest_data.py

# Opsi B — modular (package):
python -m energy_forecast.data.fetch_energy_dk
python -m energy_forecast.data.fetch_weather

# Opsi C — orkestrator:
python -m energy_forecast.orchestration.daily_pipeline
```
Output:
- `data/raw/consumption_YYYYMMDD_HHMMSS.csv` (arsip timestamp, tidak menimpa lama)
- `data/raw/consumption.csv` (latest snapshot untuk `merge_data`)
- `data/raw/weather_YYYYMMDD_HHMMSS.csv` + `data/raw/weather.csv`
- Upload ke MinIO (fail-safe: tetap sukses lokal walau MinIO offline)
- Sampel lokal: `data/raw/sample_consumption.csv`, `data/raw/sample_weather.csv` (100 baris); pointer `.dvc` dilacak Git.

#### 3. Simulasi Periodik — Rerun Tanpa Overwrite Destruktif
Setiap rerun membuat file timestamp baru:
```bash
python src/ingest_data.py
ls -lt data/raw/ | head
# -rw-r--r-- consumption_20260304_135700.csv  <-- arsip 1
# -rw-r--r-- consumption_20260304_140300.csv  <-- arsip 2 (baru, lama tetap ada)
# -rw-r--r-- consumption.csv                 <-- latest

# Verifikasi periodik 2x:
python src/ingest_data.py && python src/ingest_data.py && ls data/raw/consumption_*.csv
```
Logika ada di `src/ingest_data.py:save_with_timestamp` dan `src/energy_forecast/data/fetch_energy_dk.py:37-48` / `fetch_weather.py:16-27`.

> Penjelasan mekanisme versioning ini ada pada bagian [LK-05](#lk-05-manajemen-data-versioning-menggunakan-dvc).

#### 4. Automasi Prapemrosesan — `src/preprocess.py`
Membersihkan data mentah agar siap ekstraksi fitur / training:
```bash
python src/preprocess.py
# atau:
python -m energy_forecast.data.merge_data
```
Langkah di `src/preprocess.py` / `src/energy_forecast/data/merge_data.py:48-90`:
- Load `consumption.csv` → `drop_duplicates`, `dropna(datetime, ConsumptionMW)`, groupby DK1+DK2 → `consumption_mw`
- Load `weather.csv` → `drop_duplicates(time)`, `ffill(limit=3)` untuk gap cuaca (missing-value handling)
- `inner merge` on `datetime`, `add_time_features` (hour/day_of_week/month/is_weekend), `add_holiday_feature` (holidays.Denmark), `add_lag_features` (24h/48h/168h)
- `clean_missing_values()` → laporan `df.isna().sum()`, info `lag NaN 168 jam pertama` (wajar, di-drop saat training)
- Simpan `data/processed/merged_data.csv` + info `sample_merged_data.csv`, upload MinIO

#### 5. Sinkronisasi Repositori

Skrip `src/ingest_data.py` dan `src/preprocess.py` disimpan di Git. Dataset penuh dilacak melalui pointer DVC, sedangkan file CSV lokal diabaikan Git agar repositori tetap ringan.

### Bentuk dan Format Luaran

1. Skrip Python `src/ingest_data.py` dan `src/preprocess.py`.
2. Data mentah CSV di `data/raw/`, dengan pointer DVC yang dapat di-commit.
3. Petunjuk menjalankan ingestion dan preprocessing pada bagian ini.

## [LK-05] Manajemen Data Versioning Menggunakan DVC

Dataset mentah dari LK-4 dilacak dengan DVC melalui file penunjuk di `data/raw/*.csv.dvc`. Saat dataset bertambah, saya dapat menjalankan `dvc add` lagi dan membandingkan perubahan hash penunjuknya di Git. File CSV penuh tetap berada di luar Git, sedangkan MinIO dipakai sebagai object storage.

### Petunjuk Pengerjaan

```bash
dvc status
dvc add data/raw/consumption.csv data/raw/weather.csv
git diff -- data/raw/consumption.csv.dvc data/raw/weather.csv.dvc
# Setelah dua versi data ter-commit, bandingkan dengan: dvc diff HEAD~1 HEAD
```

### Alur Penambahan Versi Data (yang Sudah Diimplementasikan)

Setiap kali pipeline ingestion dijalankan, data **tidak pernah ditimpa secara destruktif**. Mekanisme versioning bekerja di tiga lapis:

1. **Arsip timestamp non-destruktif (lapis utama)** — `save_with_timestamp()` (`src/ingest_data.py:71-84`) dan `save_to_local()` (`src/energy_forecast/data/fetch_energy_dk.py:38-48`, `src/energy_forecast/data/fetch_weather.py:16-24`) menulis **dua** file sekaligus:
   - `data/raw/{nama}_YYYYMMDD_HHMMSS.csv` — arsip immutable dengan timestamp **UTC** (contoh: `consumption_20261011_093000.csv`)
   - `data/raw/{nama}.csv` — snapshot `latest` yang dipakai downstream (`merge_data`)

   Rerun 3x menghasilkan 3 arsip berbeda + 1 latest; file lama tidak pernah dihapus.

2. **Object storage (MinIO)** — snapshot terbaru di-upload ke bucket `energy-forecast` (dibuat otomatis bila belum ada) sebagai `raw/consumption.csv`, `raw/weather.csv`, dan `processed/merged_data.csv`. Upload memakai helper bersama di `src/energy_forecast/storage.py` dan bersifat **fail-safe**: pipeline tetap sukses walau MinIO offline.

3. **Traceability ke model (MLflow)** — setiap training run mencatat parameter data (`train_rows`, `test_rows`, `n_features`) dan mendaftarkan model ke MLflow Registry (`src/energy_forecast/models/train_baseline.py:47-71`), sehingga satu model version bisa dilacak ke run dan snapshot data yang menghasilkannya.

Alur lengkapnya:

```
[Energi Data Service / Open-Meteo API]  ← nilai "terkini", bisa direvisi
        │  fetch (requests)
        ▼
data/raw/consumption_<UTC timestamp>.csv  ← ARSIP VERSI (immutable, non-destruktif)
data/raw/consumption.csv                  ← latest snapshot (input merge_data)
        │  merge_data (deterministik: clean → merge → fitur → lag)
        ▼
data/processed/merged_data.csv            ← feature table
        │  training (MLflow run + Model Registry)
        ▼
models/baseline_model.joblib              ← tercatat: run_id, train_rows, features
```

### Cara Mereproduksi Model dari Versi Data Tertentu

Karena setiap arsip timestamp adalah **snapshot penuh** (bukan delta), reproduksi hanya butuh tiga langkah:

```bash
# 1. Pilih versi dataset yang mau direproduksi
ls -lt data/raw/consumption_*.csv

# 2. Jadikan arsip itu sebagai input preprocessing
cp data/raw/consumption_20261011_093000.csv data/raw/consumption.csv
cp data/raw/weather_20261011_093000.csv     data/raw/weather.csv

# 3. Rebuild feature table dan retrain
python -m energy_forecast.data.merge_data
python -m energy_forecast.models.train_baseline
```

Kombinasi **(kode Git commit + pointer DVC dataset + parameter model)** mencatat versi data dan konfigurasi yang dipakai dalam eksperimen.

### Mengapa Versioning Dataset Krusial untuk Reproduksibilitas Model

1. **API bersifat "moving target".** Energi Data Service dan Open-Meteo selalu mengembalikan nilai terbaru, dan data historis bisa direvisi (koreksi meter, backfill, penyesuaian DST). Tanpa snapshot, menjalankan ulang kode yang sama nyatanya menghasilkan dataset yang berbeda.

2. **Kode saja tidak cukup untuk reproduksi.** Model = f(data, kode, hyperparameter, seed). Git hanya mem-version **kode**; kalau dataset berubah diam-diam, "same code" ≠ "same model". Arsip timestamp mengunci komponen data dari persamaan itu.

3. **Debugging dan audit menjadi mungkin.** Ketika metrik memburuk (mis. MAPE naik 3% → 7%), kita bisa melatih ulang pada data versi lama vs baru untuk membuktikan apakah penyebabnya perubahan data, bukan bug kode. Ini sekaligus landasan dari drift detection yang dipakai sebagai retraining trigger di project ini.

4. **Rollback tanpa perlu fetch ulang.** Bila dataset terbaru ternyata korup (API error/429 separuh jalan), kembali ke arsip timestamp sebelumnya cukup dengan satu `cp` — tanpa harus menunggu API menyediakan ulang data historis.

5. **Kolaborasi dan CI tetap ringan.** Pointer `data/raw/sample_*.csv.dvc` dilacak Git, sementara file CSV dan dataset penuh tetap di luar Git. Data dapat diambil dari penyimpanan DVC tanpa membuat repositori membengkak.

### Keterbatasan & Roadmap

- Snapshot di MinIO saat ini menyimpan versi **latest** per object; untuk retensi penuh sisi server, object versioning S3 bisa diaktifkan pada bucket `energy-forecast` (via MinIO Console atau `mc version enable`) — arsip timestamp lokal tetap menjadi sumber kebenaran utama.
- `data/processed/merged_data.csv` ditimpa setiap run; reprodusibilitasnya dijamin oleh preprocessing yang deterministik ditambah arsip raw yang lengkap.
- DVC sudah dipakai untuk melacak dataset raw melalui pointer `.dvc`; pengembangan berikutnya adalah menyimpan beberapa versi objek MinIO agar arsip di remote juga dapat diaudit.

### Bentuk Luaran

1. Pointer `data/raw/*.csv.dvc` dan aturan `.gitignore` untuk dataset.
2. Screenshot lokal `dvc status` atau `dvc diff` ketika memperlihatkan perubahan dua versi data.
3. Penjelasan alur penambahan versi data pada README ini.

## [LK-6] Manajemen Eksperimen dan Pelacakan Metrik Pemodelan dengan MLflow

Proyek LK-01 ini memakai regresi untuk memprediksi konsumsi listrik Denmark. Pada tahap ini saya menggunakan MLflow untuk mencatat tiga variasi hyperparameter dan membandingkan hasilnya melalui dashboard.

### Metode Pengerjaan Aktivitas

#### Eksperimen tiga variasi dengan MLflow

`src/energy_forecast/models/train.py` memakai ulang
`energy_forecast.models.train_baseline` untuk tiga kombinasi Random Forest.
Dataset latih adalah `data/processed/merged_data.csv`; skrip memeriksa
bahwa `consumption.csv` dan `weather.csv` sesuai hash pada pointer DVC LK-05.
Ketiga run memakai split kronologis yang sama (80% latih, 20% uji) dan mencatat
parameter, hash dataset, RMSE, MAE, MAPE, serta artefak model. Run dengan RMSE
terendah didaftarkan ke MLflow Model Registry dan disimpan sebagai
`models/baseline_model.joblib` untuk kode prediksi yang sudah ada.

```bash
pip install -e .
# Jika data/raw/*.csv belum tersedia: dvc pull
python src/preprocess.py
mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns
# Di terminal Codespaces kedua:
python -m energy_forecast.models.train
```

Buka tab **Ports** Codespaces untuk port 5000, lalu di MLflow UI pilih eksperimen
`energy-forecast-baseline` > **Training runs**. Tampilan grafik di sebelah daftar
run memperlihatkan perbandingan MAE, MAPE, dan RMSE. Luaran pelaksanaan tersimpan
secara lokal di `docs/` (diabaikan Git, kecuali `.gitkeep`):
`docs/experiment_results.csv`, `docs/model_metadata.md`, dan
`docs/report_mlflow.pdf` (berisi screenshot UI Docker). Berkas laporan dan
skrip pembuat PDF disimpan lokal untuk kebutuhan tugas pribadi.

Screenshot laporan saat ini diambil dari **MLflow 2.10 dalam Docker lokal**
pada port 5000. Daftar UI menampilkan enam run karena tiga variasi dijalankan
dua kali saat pengujian integrasi; CSV dan metadata menunjukkan eksekusi terakhir
yang memilih Registry versi 2. Folder `docs/` diabaikan Git (kecuali `.gitkeep`),
sehingga bukti dashboard perlu dibuat ulang di Codespaces jika dosen
mensyaratkan lingkungan tersebut.

### Bentuk dan Format Luaran

1. Kode pelatihan: `src/energy_forecast/models/train.py`, dengan logging parameter, metrik, dan model ke MLflow.
2. Laporan teknis PDF: `docs/report_mlflow.pdf`, berisi screenshot daftar run dan grafik perbandingan metrik.
3. Metadata model: `docs/model_metadata.md` dan ringkasan run di `docs/experiment_results.csv`.

## Running (MLOps Pipeline Umum)

### Daily data pipeline (orkestrasi)

Fetch new data dan rebuild feature table (menggabungkan ingestion dan preprocessing pada LK-4 melalui orchestrator):

```bash
python -m energy_forecast.orchestration.daily_pipeline
# ekuivalen dengan:
# python src/ingest_data.py && python src/preprocess.py
# atau:
# python -m energy_forecast.data.fetch_energy_dk && python -m energy_forecast.data.fetch_weather && python -m energy_forecast.data.merge_data
```

Data disimpan lokal ke `data/raw/` (timestamped + latest) dan `data/processed/`, plus upload ke **MinIO**.

### Drill: cek file mentah & processed

```bash
ls -lh data/raw/consumption*.csv data/raw/weather*.csv
head data/raw/sample_consumption.csv
python -c "import pandas as pd; print(pd.read_csv('data/processed/merged_data.csv').shape); print(pd.read_csv('data/processed/merged_data.csv').isna().sum())"
```

### Drift detection

Run the 5-signal drift detection:

```bash
python -m energy_forecast.monitoring.detect_drift
```

Signals: PSI (peak hours), night/day ratio, mean consumption shift, peak hour shift, z-score.

### Training with MLflow

```bash
python -m energy_forecast.models.train_baseline
python -m energy_forecast.models.train_deep_learning
```

Both scripts log metrics (RMSE, MAPE) and register models to the **MLflow Registry**.

### Model serving (FastAPI)

```bash
python -m uvicorn energy_forecast.serving.serve_model:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /health` — health check
- `POST /predict` — predict next N hours of consumption

Swagger docs available at `http://localhost:8000/docs`.

### Scheduled runs (Airflow)

Place the DAG file at `dags/energy_forecast_dag.py` and trigger via Airflow UI or CLI:

```bash
airflow dags list
airflow dags test energy_forecast_daily
```

## Docker Deployment

Jalankan stack Docker lokal (API + MinIO + MLflow + Prometheus + Grafana):

```bash
docker compose up -d --build
docker compose ps
```

Container MinIO yang baru masih kosong. Untuk memakai dataset DVC LK-05 yang
sudah ada di `data/raw/`, unggah file tanpa mengubah isinya, jalankan tiga
eksperimen terhadap MLflow Docker, lalu mulai ulang API agar memuat versi model
terbaru dari Registry:

```bash
pip install -e .
# Jika data/raw/*.csv belum tersedia: dvc pull
python src/preprocess.py
python -m energy_forecast.data.sync_to_minio
python -m energy_forecast.models.train
docker compose restart api
```

`energy_forecast.data.sync_to_minio` memeriksa hash raw terhadap pointer DVC dan
membandingkan MD5 objek MinIO dengan file lokal setelah upload. Cek bucket
`energy-forecast` di MinIO Console (`http://localhost:9001`), run dan model
Registry di MLflow (`http://localhost:5000`), serta `GET /health` dan
`POST /predict` di API (`http://localhost:8000/docs`). Database dan artefak
MLflow Docker disimpan dalam volume `mlflow-data`; data MinIO dalam `minio-data`.
Stack ini berjalan lokal untuk uji integrasi, dengan konfigurasi kredensial
pengembangan dari `docker-compose.yml`.

Services:
| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI prediction service |
| MinIO API | 9000 | S3-compatible object storage |
| MinIO Console | 9001 | Object storage admin UI |
| MLflow | 5000 | Experiment tracking & model registry |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3000 | Dashboards (admin/admin) |

## Configuration

All parameters live in `src/energy_forecast/config.py`:

| Variable | Description | Default |
|----------|-------------|---------|
| `COUNTRY` | Country code | `DK` |
| `TIMEZONE` | Timezone | `Europe/Copenhagen` |
| `LATITUDE`, `LONGITUDE` | Coordinates for weather | `55.6761`, `12.5683` |
| `ENERGIDATA_DATASET_URL` | Energi Data Service API URL | ... |
| `DATA_START_DATE` | Start date for fetching data | `2026-01-01` |
| `FETCH_LIMIT` | Maximum number of records | `10000` |
| `PROJECT_ROOT` | Root directory for data/models/logs in installed/containerized runs | auto-detected, `/app` in Docker |
| `MINIO_ENDPOINT` | MinIO object storage URL | `http://localhost:9000` |
| `MINIO_ACCESS_KEY` | MinIO access key | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO secret key | `minioadmin` |
| `MINIO_BUCKET` | MinIO bucket name | `energy-forecast` |
| `MLFLOW_TRACKING_URI` | MLflow tracking server URL | `http://localhost:5000` |

## MLOps Pipeline

1. **Ingestion** — `energy_forecast.data.fetch_energy_dk` downloads raw consumption data and uploads to MinIO.
2. **Weather ingestion** — `energy_forecast.data.fetch_weather` downloads weather data from Open-Meteo.
3. **Feature engineering** — `energy_forecast.data.merge_data` combines both, adds time/holiday/lag features, uploads to MinIO.
4. **Drift detection** — `energy_forecast.monitoring.detect_drift` calculates 5 drift signals.
5. **Daily orchestration** — `energy_forecast.orchestration.daily_pipeline` or **Airflow DAG** runs the full pipeline.
6. **Training** — `energy_forecast.models.train_baseline` / `train_deep_learning` train models with MLflow tracking.
7. **Prediction** — `energy_forecast.predict.predict_future` forecasts the next 24h.
8. **Monitoring** — `evaluate_model` + `check_trigger` detect drift and auto-retrain (MAPE > 5% OR drift signals exceeded).
9. **Serving** — FastAPI serves predictions via REST API, containerized with Docker.

## Troubleshooting

**Error 429 (Rate limit)** — Energi Data Service limits request frequency. Wait a few minutes and rerun.

**Error 404** — The dataset may have been renamed or removed. Check the dataset catalog at `https://api.energidataservice.dk/meta/dataset`.

**MinIO connection refused** — Ensure MinIO is running locally on port 9000.

**MinIO image not found / 401 Unauthorized** — The official `minio/minio` (Docker Hub) and `quay.io/minio/minio` images are no longer pullable. Use the community-maintained S3-compatible fork instead:

```bash
docker run -d --name minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  pgsty/silo server /data --console-address ":9001"
```

**MLflow connection refused** — Ensure MLflow server is running: `mlflow server --port 5000`.
