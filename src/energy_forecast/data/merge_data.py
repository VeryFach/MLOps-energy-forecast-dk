import io

import holidays
import pandas as pd
from minio import Minio

from energy_forecast.config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    PROCESSED_DIR,
    RAW_DIR,
)


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


def save_to_minio(df: pd.DataFrame) -> None:
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
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
    print(f"Uploaded merged_data.csv to MinIO bucket '{MINIO_BUCKET}'")


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

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "merged_data.csv"
    merged.to_csv(out_path, index=False)
    print(f"Saved {len(merged)} records to {out_path}")

    save_to_minio(merged)
    register_feast_features(merged)


if __name__ == "__main__":
    main()
