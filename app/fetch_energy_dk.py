import requests
import pandas as pd
from pathlib import Path

from config import ENERGIDATA_DATASET_URL, DATA_START_DATE, FETCH_LIMIT, CONSUMPTION_FIELD

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
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

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "consumption.csv"
    consumption.to_csv(out_path, index=False)

    print(f"Saved {len(consumption)} records to {out_path}")


if __name__ == "__main__":
    main()