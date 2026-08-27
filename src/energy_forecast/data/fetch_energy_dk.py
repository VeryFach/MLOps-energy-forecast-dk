import io

import pandas as pd
import requests
from minio import Minio

from energy_forecast.config import (
    CONSUMPTION_FIELD,
    DATA_START_DATE,
    ENERGIDATA_DATASET_URL,
    FETCH_LIMIT,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    RAW_DIR,
)


def fetch_from_api() -> pd.DataFrame:
    params = {
        "start": DATA_START_DATE,
        "limit": FETCH_LIMIT,
        "sort": "TimeUTC ASC",
    }
    response = requests.get(ENERGIDATA_DATASET_URL, params=params)
    response.raise_for_status()

    records = response.json()["records"]
    df = pd.DataFrame(records)

    consumption = df[["TimeUTC", "TimeDK", "PriceArea", CONSUMPTION_FIELD]].copy()
    consumption.rename(columns={CONSUMPTION_FIELD: "ConsumptionMW"}, inplace=True)
    return consumption


def save_to_local(df: pd.DataFrame) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "consumption.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")


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
        "raw/consumption.csv",
        csv_buffer,
        length=len(csv_bytes),
        content_type="text/csv",
    )
    print(f"Uploaded consumption.csv to MinIO bucket '{MINIO_BUCKET}'")


def main():
    df = fetch_from_api()
    save_to_local(df)
    save_to_minio(df)


if __name__ == "__main__":
    main()