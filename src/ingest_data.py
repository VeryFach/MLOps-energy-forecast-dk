"""
ingest_data.py — Skrip Penarikan Data Dinamis (Data Ingestion)

Memenuhi rubrik:
  - File `src/ingest_data.py` di folder `src/`
  - Menggunakan `requests` untuk mengambil data dinamis (Energi Data Service + Open-Meteo)
  - Simulasi periodik: rerun tanpa menimpa data lama secara destruktif (timestamp pada nama file)
  - Juga meng-update `consumption.csv` / `weather.csv` sebagai snapshot terbaru untuk pipeline downstream

Cara jalan (GitHub Codespaces):
  python src/ingest_data.py
  # atau modul:
  python -m energy_forecast.data.fetch_energy_dk
  python -m energy_forecast.data.fetch_weather

Output:
  data/raw/consumption_YYYYMMDD_HHMMSS.csv  (arsip non-destruktif)
  data/raw/consumption.csv                  (latest snapshot)
  data/raw/weather_YYYYMMDD_HHMMSS.csv
  data/raw/weather.csv
  + upload ke MinIO bucket `energy-forecast` (jika MinIO tersedia, fail-safe)
"""

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from minio import Minio

# --- Pastikan import `energy_forecast` bekerja saat dijalankan sebagai `python src/ingest_data.py` ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from energy_forecast.config import (  # noqa: E402
    CONSUMPTION_FIELD,
    DATA_START_DATE,
    ENERGIDATA_DATASET_URL,
    FETCH_LIMIT,
    HISTORY_START_DATE,
    LATITUDE,
    LONGITUDE,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    OPEN_METEO_ARCHIVE_URL,
    RAW_DIR,
    WEATHER_VARIABLES,
)


def fetch_energy_from_api() -> pd.DataFrame:
    """Tarik data konsumsi DK1/DK2 dari Energi Data Service (Requests)."""
    params = {
        "start": DATA_START_DATE,
        "limit": FETCH_LIMIT,
        "sort": "TimeUTC ASC",
    }
    print(f"[ingest] Fetching energy data from {ENERGIDATA_DATASET_URL} ...")
    response = requests.get(ENERGIDATA_DATASET_URL, params=params, timeout=30)
    response.raise_for_status()
    records = response.json()["records"]
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("API mengembalikan 0 records. Cek DATA_START_DATE / FETCH_LIMIT / dataset URL.")
    consumption = df[["TimeUTC", "TimeDK", "PriceArea", CONSUMPTION_FIELD]].copy()
    consumption.rename(columns={CONSUMPTION_FIELD: "ConsumptionMW"}, inplace=True)
    print(f"[ingest] Fetched {len(consumption)} energy records (DK1+DK2 combined).")
    return consumption


def fetch_weather_from_api() -> pd.DataFrame:
    """Tarik data cuaca Copenhagen dari Open-Meteo Archive (Requests)."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": HISTORY_START_DATE,
        "end_date": datetime.now(tz=timezone.utc).date().isoformat(),
        "hourly": WEATHER_VARIABLES,
    }
    print(f"[ingest] Fetching weather from {OPEN_METEO_ARCHIVE_URL} ...")
    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=30)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    weather = pd.DataFrame(hourly)
    print(f"[ingest] Fetched {len(weather)} weather records ({HISTORY_START_DATE} -> today).")
    return weather


def save_with_timestamp(df: pd.DataFrame, stem: str) -> tuple[Path, Path]:
    """Simpan DataFrame ke `data/raw/{stem}_{timestamp}.csv` + `data/raw/{stem}.csv` (latest).

    Simulasi periodik: setiap rerun membuat file timestamp baru tanpa menghapus arsip lama.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_path = RAW_DIR / f"{stem}_{timestamp}.csv"
    latest_path = RAW_DIR / f"{stem}.csv"
    df.to_csv(timestamped_path, index=False)
    df.to_csv(latest_path, index=False)
    print(f"[ingest] Saved {len(df)} records to {timestamped_path}")
    print(f"[ingest] Updated latest snapshot to {latest_path} (timestamped copy preserved, non-destructive)")
    return timestamped_path, latest_path


def upload_to_minio(df: pd.DataFrame, object_name: str) -> None:
    """Upload ke MinIO (fail-safe: tidak menggagalkan ingestion jika MinIO offline)."""
    try:
        client = Minio(
            MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_ENDPOINT.startswith("https://"),
        )
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        csv_buffer = io.BytesIO(csv_bytes)
        client.put_object(
            MINIO_BUCKET,
            f"raw/{object_name}",
            csv_buffer,
            length=len(csv_bytes),
            content_type="text/csv",
        )
        print(f"[ingest] Uploaded {object_name} to MinIO bucket '{MINIO_BUCKET}'")
    except Exception as e:
        print(f"[ingest] WARNING: MinIO upload skipped ({e}). Data tetap tersimpan lokal.")


def ingest_all() -> None:
    """Jalankan ingestion untuk kedua sumber secara berurutan."""
    # Energy
    try:
        df_energy = fetch_energy_from_api()
        save_with_timestamp(df_energy, "consumption")
        upload_to_minio(df_energy, "consumption.csv")
    except Exception as e:
        print(f"[ingest] ERROR energy ingestion failed: {e}")
        raise

    # Weather
    try:
        df_weather = fetch_weather_from_api()
        save_with_timestamp(df_weather, "weather")
        upload_to_minio(df_weather, "weather.csv")
    except Exception as e:
        print(f"[ingest] ERROR weather ingestion failed: {e}")
        raise

    print("[ingest] Done. Rerun kapan pun untuk arsip baru tanpa menghapus data lama.")


def main():
    ingest_all()


if __name__ == "__main__":
    main()
