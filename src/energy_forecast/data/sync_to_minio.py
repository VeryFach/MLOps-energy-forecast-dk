"""Upload checked-out LK-05 datasets to MinIO without changing file bytes."""

import hashlib
import re

from energy_forecast.config import MINIO_BUCKET, PROCESSED_DIR, RAW_DIR
from energy_forecast.storage import get_minio_client


def main():
    files = [
        (RAW_DIR / "consumption.csv", "raw/consumption.csv"),
        (RAW_DIR / "weather.csv", "raw/weather.csv"),
        (PROCESSED_DIR / "merged_data.csv", "processed/merged_data.csv"),
    ]
    client = get_minio_client()
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    for path, object_name in files:
        if not path.is_file():
            raise FileNotFoundError(f"Dataset tidak ditemukan: {path}")
        local_md5 = hashlib.md5(path.read_bytes()).hexdigest()
        if path.parent == RAW_DIR:
            pointer = path.with_name(path.name + ".dvc")
            match = re.search(
                r"(?m)^\s*-\s*md5:\s*([0-9a-f]{32})\s*$", pointer.read_text()
            )
            if not match or local_md5 != match.group(1):
                raise ValueError(
                    f"Hash {path} tidak cocok dengan pointer DVC: {pointer}"
                )

        client.fput_object(
            MINIO_BUCKET, object_name, str(path), content_type="text/csv"
        )
        response = client.get_object(MINIO_BUCKET, object_name)
        try:
            remote_md5 = hashlib.md5(response.read()).hexdigest()
        finally:
            response.close()
            response.release_conn()
        if remote_md5 != local_md5:
            raise ValueError(f"Verifikasi upload gagal: {object_name}")
        print(f"{MINIO_BUCKET}/{object_name}: MD5 {remote_md5} OK")


if __name__ == "__main__":
    main()
