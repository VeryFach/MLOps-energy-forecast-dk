import requests
import pandas as pd
from datetime import date
from pathlib import Path

from config import (
    LATITUDE,
    LONGITUDE,
    OPEN_METEO_ARCHIVE_URL,
    HISTORY_START_DATE,
    WEATHER_VARIABLES,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": HISTORY_START_DATE,
        "end_date": date.today().isoformat(),
        "hourly": WEATHER_VARIABLES,
    }

    response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params)
    response.raise_for_status()

    hourly = response.json()["hourly"]
    weather = pd.DataFrame(hourly)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "weather.csv"
    weather.to_csv(out_path, index=False)

    print(f"Saved {len(weather)} records to {out_path}")


if __name__ == "__main__":
    main()