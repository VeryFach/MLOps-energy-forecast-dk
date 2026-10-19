import holidays
import pandas as pd

from energy_forecast.config import (
    PROCESSED_DIR,
    RAW_DIR,
)
from energy_forecast.storage import upload_dataframe_csv_to_minio


def load_consumption():
    df = pd.read_csv(RAW_DIR / "consumption.csv")
    df["datetime"] = pd.to_datetime(df["TimeDK"])
    national = df.groupby("datetime")["ConsumptionMW"].sum().reset_index()
    national.rename(columns={"ConsumptionMW": "consumption_mw"}, inplace=True)
    return national


def load_weather():
    df = pd.read_csv(RAW_DIR / "weather.csv")
    df["datetime"] = pd.to_datetime(df["time"])
    df = df[["datetime", "temperature_2m", "relativehumidity_2m", "windspeed_10m"]]
    return df


def add_time_features(df):
    df["hour"] = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.dayofweek
    df["month"] = df["datetime"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    return df


def add_holiday_feature(df):
    dk_holidays = holidays.Denmark(
        years=range(df["datetime"].dt.year.min(), df["datetime"].dt.year.max() + 1)
    )
    df["is_holiday_dk"] = df["datetime"].dt.date.isin(dk_holidays).astype(int)
    return df


def add_lag_features(df):
    df = df.sort_values("datetime").reset_index(drop=True)
    df["consumption_lag_24h"] = df["consumption_mw"].shift(24)
    df["consumption_lag_48h"] = df["consumption_mw"].shift(48)
    df["consumption_lag_168h"] = df["consumption_mw"].shift(168)
    return df


def clean_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Pembersihan missing values untuk persiapan feature engineering.

    - Laporan jumlah missing per kolom.
    - Forward-fill untuk gap cuaca singkat (jika ada).
    - Lag features (168 jam pertama) sengaja dipertahankan sebagai NaN
      agar downstream training bisa memutuskan dropna/fill secara eksplisit.
    """
    missing_before = df.isna().sum()
    if missing_before.sum() > 0:
        print("Missing values sebelum cleaning:")
        print(missing_before[missing_before > 0])

    # Contoh pembersihan generik: forward-fill sisa gap kecil (max 3 jam)
    # Tidak mengisi lag NaN yang memang butuh history 168 jam
    weather_cols = ["temperature_2m", "relativehumidity_2m", "windspeed_10m"]
    for col in weather_cols:
        if col in df.columns:
            df[col] = df[col].ffill(limit=3)

    missing_after = df.isna().sum()
    if missing_after.sum() > 0:
        print("Missing values setelah cleaning (sisa NaN lag awal wajar):")
        print(missing_after[missing_after > 0])
    else:
        print("Tidak ada missing values setelah cleaning.")

    # Info tambahan: berapa baris yang akan ter-drop jika training
    lag_cols = ["consumption_lag_24h", "consumption_lag_48h", "consumption_lag_168h"]
    n_drop = df[lag_cols].isna().any(axis=1).sum() if all(c in df.columns for c in lag_cols) else 0
    print(f"Baris dengan lag NaN (butuh drop sebelum training): {n_drop}/{len(df)}")
    return df


def save_to_minio(df: pd.DataFrame) -> None:
    upload_dataframe_csv_to_minio(df, "processed/merged_data.csv", "[merge_data]")


def register_feast_features(df: pd.DataFrame) -> None:
    try:
        from feast import Entity, Field, RepoSource
        from feast.types import Float32, Int64

        entity = Entity(name="datetime", join_keys=["datetime"])  # noqa: F841

        source = RepoSource(  # noqa: F841
            path=str(PROCESSED_DIR / "merged_data.csv"),
            timestamp_field="datetime",
        )

        feature_view_fields = [  # noqa: F841
            Field(name="consumption_mw", dtype=Float32),
            Field(name="temperature_2m", dtype=Float32),
            Field(name="relativehumidity_2m", dtype=Float32),
            Field(name="windspeed_10m", dtype=Float32),
            Field(name="hour", dtype=Int64),
            Field(name="day_of_week", dtype=Int64),
            Field(name="month", dtype=Int64),
            Field(name="is_weekend", dtype=Int64),
            Field(name="is_holiday_dk", dtype=Int64),
        ]

        print(
            "Feast feature store registration skipped (configure Feast repo to enable)."
        )
    except ImportError:
        print("Feast not installed. Skipping feature store registration.")


def main():
    consumption = load_consumption()
    weather = load_weather()

    merged = pd.merge(consumption, weather, on="datetime", how="inner")
    merged = add_time_features(merged)
    merged = add_holiday_feature(merged)
    merged = add_lag_features(merged)
    merged = clean_missing_values(merged)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "merged_data.csv"
    merged.to_csv(out_path, index=False)
    print(f"Saved {len(merged)} records to {out_path}")

    save_to_minio(merged)
    register_feast_features(merged)


if __name__ == "__main__":
    main()
