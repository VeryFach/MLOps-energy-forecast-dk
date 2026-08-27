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

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "weather.csv"
    weather.to_csv(out_path, index=False)

    print(f"Saved {len(weather)} records to {out_path}")


if __name__ == "__main__":
    main()
