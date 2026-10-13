from datetime import datetime, timezone

import pandas as pd
import requests

from energy_forecast.config import (
    HISTORY_START_DATE,
    LATITUDE,
    LONGITUDE,
    OPEN_METEO_ARCHIVE_URL,
    RAW_DIR,
    WEATHER_VARIABLES,
)
from energy_forecast.storage import upload_dataframe_csv_to_minio


def save_to_local(df: pd.DataFrame) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_path = RAW_DIR / f"weather_{timestamp}.csv"
    latest_path = RAW_DIR / "weather.csv"
    df.to_csv(timestamped_path, index=False)
    df.to_csv(latest_path, index=False)
    print(f"Saved {len(df)} records to {timestamped_path}")
    print(f"Updated latest snapshot to {latest_path} (timestamped copy preserved)")


def save_to_minio(df: pd.DataFrame) -> None:
    upload_dataframe_csv_to_minio(df, "raw/weather.csv", "[fetch_weather]")


def main():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": HISTORY_START_DATE,
        "end_date": datetime.now(tz=timezone.utc).date().isoformat(),
        "hourly": WEATHER_VARIABLES,
    }

    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params)
    response.raise_for_status()

    hourly = response.json()["hourly"]
    weather = pd.DataFrame(hourly)

    save_to_local(weather)
    save_to_minio(weather)


if __name__ == "__main__":
    main()
