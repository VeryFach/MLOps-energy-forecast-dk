import time
from datetime import datetime, timezone

import pandas as pd
import requests

from energy_forecast.config import (
    CONSUMPTION_FIELD,
    DATA_START_DATE,
    ENERGIDATA_DATASET_URL,
    FETCH_LIMIT,
    RAW_DIR,
)
from energy_forecast.storage import upload_dataframe_csv_to_minio

MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 5.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return DEFAULT_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))


def _get_with_retry(url: str, params: dict) -> requests.Response:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = requests.get(url, params=params, timeout=60)
        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response
        if attempt == MAX_ATTEMPTS:
            response.raise_for_status()
        delay = _retry_delay(response, attempt)
        print(
            f"[fetch_energy] HTTP {response.status_code}; "
            f"retry {attempt}/{MAX_ATTEMPTS - 1} in {delay:g}s",
            flush=True,
        )
        time.sleep(delay)
    raise RuntimeError("unreachable")


def fetch_from_api() -> pd.DataFrame:
    params = {
        "start": DATA_START_DATE,
        "limit": FETCH_LIMIT,
        "sort": "TimeUTC ASC",
    }
    response = _get_with_retry(ENERGIDATA_DATASET_URL, params)

    records = response.json()["records"]
    df = pd.DataFrame(records)

    consumption = df[["TimeUTC", "TimeDK", "PriceArea", CONSUMPTION_FIELD]].copy()
    consumption.rename(columns={CONSUMPTION_FIELD: "ConsumptionMW"}, inplace=True)
    return consumption


def save_to_local(df: pd.DataFrame) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_path = RAW_DIR / f"consumption_{timestamp}.csv"
    latest_path = RAW_DIR / "consumption.csv"
    # Save timestamped copy (non-destructive history)
    df.to_csv(timestamped_path, index=False)
    # Update latest snapshot for downstream pipeline
    df.to_csv(latest_path, index=False)
    print(f"Saved {len(df)} records to {timestamped_path}")
    print(f"Updated latest snapshot to {latest_path} (timestamped copy preserved)")


def save_to_minio(df: pd.DataFrame) -> None:
    upload_dataframe_csv_to_minio(df, "raw/consumption.csv", "[fetch_energy]")


def main():
    df = fetch_from_api()
    save_to_local(df)
    save_to_minio(df)


if __name__ == "__main__":
    main()
