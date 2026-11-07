import io
from urllib.parse import urlparse

import pandas as pd
from minio import Minio

from energy_forecast.config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
)


def _minio_endpoint_and_secure(endpoint: str) -> tuple[str, bool]:
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        return parsed.netloc, parsed.scheme == "https"
    return endpoint, False


def get_minio_client() -> Minio:
    endpoint, secure = _minio_endpoint_and_secure(MINIO_ENDPOINT)
    return Minio(
        endpoint,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=secure,
    )


def upload_dataframe_csv_to_minio(
    df: pd.DataFrame,
    object_name: str,
    log_prefix: str,
) -> bool:
    """Upload a DataFrame CSV to MinIO without failing the local pipeline."""
    try:
        client = get_minio_client()
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)

        csv_bytes = df.to_csv(index=False).encode("utf-8")
        client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(csv_bytes),
            length=len(csv_bytes),
            content_type="text/csv",
        )
        print(f"{log_prefix} Uploaded {object_name} to MinIO bucket '{MINIO_BUCKET}'")
        return True
    except Exception as exc:  # noqa: BLE001 - ingestion must retain its local copy
        print(
            f"{log_prefix} WARNING: MinIO upload skipped ({exc}). Data tetap tersimpan lokal."
        )
        return False
