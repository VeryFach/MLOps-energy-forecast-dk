import io
import sys
from pathlib import Path

import holidays
import pandas as pd
from minio import Minio

# --- Pastikan import `energy_forecast` bekerja saat dijalankan sebagai `python src/preprocess.py` ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from energy_forecast.config import (  # noqa: E402
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    PROCESSED_DIR,
    RAW_DIR,
)


def load_consumption() -> pd.DataFrame:
    """Load & agregasi konsumsi nasional (DK1+DK2 -> sum) per datetime."""
    path = RAW_DIR / "consumption.csv"
    if not path.exists():
        raise FileNotFoundError(f"Tidak menemukan {path}. Jalankan `python src/ingest_data.py` dulu.")
    df = pd.read_csv(path)
    # Bersihkan duplikat jika ada (misal rerun ingestion append)
    df = df.drop_duplicates()
    # Pastikan tipe datetime
    df["datetime"] = pd.to_datetime(df["TimeDK"], errors="coerce")
    # Drop baris dengan datetime invalid (missing value handling)
    before = len(df)
    df = df.dropna(subset=["datetime", "ConsumptionMW"])
    if len(df) < before:
        print(f"[preprocess] Dropped {before - len(df)} baris consumption dengan datetime/ConsumptionMW NaN")
    national = df.groupby("datetime", as_index=False)["ConsumptionMW"].sum()
    national.rename(columns={"ConsumptionMW": "consumption_mw"}, inplace=True)
    print(f"[preprocess] Loaded consumption: {len(national)} jam unik (dari {before} records mentah)")
    return national


def load_weather() -> pd.DataFrame:
    """Load cuaca per jam, handling missing values."""
    path = RAW_DIR / "weather.csv"
    if not path.exists():
        raise FileNotFoundError(f"Tidak menemukan {path}. Jalankan `python src/ingest_data.py` dulu.")
    df = pd.read_csv(path)
    df = df.drop_duplicates(subset=["time"])
    df["datetime"] = pd.to_datetime(df["time"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["datetime"])
    cols = [c for c in ["temperature_2m", "relativehumidity_2m", "windspeed_10m"] if c in df.columns]
    # Forward-fill gap cuaca singkat (max 3 jam) - contoh pembersihan missing values
    for col in cols:
        n_missing = df[col].isna().sum()
        if n_missing > 0:
            print(f"[preprocess] Missing {col}: {n_missing} -> ffill(limit=3)")
            df[col] = df[col].ffill(limit=3)
    df = df[["datetime"] + cols]
    print(f"[preprocess] Loaded weather: {len(df)} records")
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df["hour"] = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.dayofweek
    df["month"] = df["datetime"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    return df


def add_holiday_feature(df: pd.DataFrame) -> pd.DataFrame:
    dk_holidays = holidays.Denmark(
        years=range(df["datetime"].dt.year.min(), df["datetime"].dt.year.max() + 1)
    )
    df["is_holiday_dk"] = df["datetime"].dt.date.isin(dk_holidays).astype(int)
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("datetime").reset_index(drop=True)
    df["consumption_lag_24h"] = df["consumption_mw"].shift(24)
    df["consumption_lag_48h"] = df["consumption_mw"].shift(48)
    df["consumption_lag_168h"] = df["consumption_mw"].shift(168)
    return df


def clean_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Laporan & pembersihan missing values generik."""
    missing_before = df.isna().sum()
    if missing_before.sum() > 0:
        print("[preprocess] Missing values sebelum cleaning:")
        print(missing_before[missing_before > 0].to_string())
    # Weather sudah di-ffill di load_weather; lag NaN di 168 jam pertama dipertahankan
    # agar downstream bisa pilih dropna/fill sesuai kebutuhan training
    lag_cols = ["consumption_lag_24h", "consumption_lag_48h", "consumption_lag_168h"]
    n_lag_nan = df[lag_cols].isna().any(axis=1).sum() if all(c in df.columns for c in lag_cols) else 0
    print(f"[preprocess] Baris dengan lag NaN (wajar 168 jam pertama): {n_lag_nan}/{len(df)}")
    # Tidak drop di sini; biarkan `merged_data.csv` lengkap, training yang akan dropna
    return df


def save_processed(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "merged_data.csv"
    df.to_csv(out_path, index=False)
    print(f"[preprocess] Saved {len(df)} records to {out_path}")
    print(f"[preprocess] Kolom: {list(df.columns)}")
    # Juga simpan versi ter-clean (drop lag NaN) sebagai contoh siap training
    clean_path = PROCESSED_DIR / "merged_data_clean.csv"
    df_clean = df.dropna(subset=["consumption_lag_168h"]).reset_index(drop=True)
    print(f"[preprocess] Info: {len(df_clean)}/{len(df)} baris tanpa lag NaN (siap training). Simpan preview ke {clean_path} jika diperlukan.")
    # Tidak wajib save clean versi, tapi beri info
    return out_path


def upload_to_minio(df: pd.DataFrame) -> None:
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
            "processed/merged_data.csv",
            csv_buffer,
            length=len(csv_bytes),
            content_type="text/csv",
        )
        print(f"[preprocess] Uploaded merged_data.csv to MinIO bucket '{MINIO_BUCKET}'")
    except Exception as e:
        print(f"[preprocess] WARNING: MinIO upload skipped ({e}). Data tetap tersimpan lokal.")


def main():
    print("[preprocess] Memulai prapemrosesan...")
    consumption = load_consumption()
    weather = load_weather()
    merged = pd.merge(consumption, weather, on="datetime", how="inner")
    print(f"[preprocess] After inner merge: {len(merged)} records")
    if merged.empty:
        raise ValueError("Hasil merge kosong. Cek overlap datetime consumption vs weather.")

    merged = add_time_features(merged)
    merged = add_holiday_feature(merged)
    merged = add_lag_features(merged)
    merged = clean_missing_values(merged)

    save_processed(merged)
    upload_to_minio(merged)
    print("[preprocess] Selesai. Data siap untuk feature extraction / training.")


if __name__ == "__main__":
    main()
