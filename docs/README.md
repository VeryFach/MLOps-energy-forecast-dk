# Energy Forecast DK — Documentation

This guide explains how to run the full data pipeline and how to refresh the CSV data files.

## Overview

The pipeline consists of three scripts in `app/`:

| Script | Purpose | Output |
|--------|---------|--------|
| `fetch_energy_dk.py` | Download hourly electricity consumption (MW) for DK1 & DK2 | `data/raw/consumption.csv` |
| `fetch_weather.py` | Download hourly weather for Copenhagen | `data/raw/weather.csv` |
| `merge_data.py` | Combine both datasets, add time/holiday/lag features | `data/processed/merged_data.csv` |

## Requirements

Install dependencies (from the project root):

```bash
pip install requests pandas holidays
```

## Running the pipeline

Run the scripts in order. From the project root:

```bash
python app/fetch_energy_dk.py
python app/fetch_weather.py
python app/merge_data.py
```

Expected output:

```
Saved 10000 records to ...\data\raw\consumption.csv
Saved 14328 records to ...\data\raw\weather.csv
Saved 5000 records to ...\data\processed\merged_data.csv
```

## How to update the CSV data

To fetch new/updated data, simply re-run the scripts above. They overwrite the existing CSVs.

- **Consumption** — fetches records from `DATA_START_DATE` up to `FETCH_LIMIT` records, so newer data is included on each run.
- **Weather** — always fetches from `HISTORY_START_DATE` to *today* (`end_date = today`), so re-running captures the latest days.
- **Merged** — rebuilds the feature table from the two raw CSVs.

### Configuring the data window

All parameters live in `app/config.py`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_START_DATE` | Start date for consumption fetch | `2026-01-01` |
| `HISTORY_START_DATE` | Start date for weather fetch | `2026-01-01` |
| `FETCH_LIMIT` | Max records from Energi Data Service | `10000` |

### Update procedure

1. (Optional) Change the date range in `app/config.py`.
2. Run the fetch scripts, then the merge script:

```bash
python app/fetch_energy_dk.py
python app/fetch_weather.py
python app/merge_data.py
```

3. Verify the output files:

```bash
python -c "import pandas as pd; print(pd.read_csv('data/processed/merged_data.csv').shape)"
```

## Output schema

### data/raw/consumption.csv

| Column | Description |
|--------|-------------|
| `TimeUTC` | Timestamp in UTC |
| `TimeDK` | Danish local time |
| `PriceArea` | DK1 (West) / DK2 (East) |
| `ConsumptionMW` | Gross consumption in MW |

### data/raw/weather.csv

| Column | Description |
|--------|-------------|
| `time` | Hourly timestamp (local time) |
| `temperature_2m` | Temperature in °C |
| `relativehumidity_2m` | Relative humidity in % |
| `windspeed_10m` | Wind speed in km/h |

### data/processed/merged_data.csv

| Column | Description |
|--------|-------------|
| `datetime` | Hourly timestamp (Danish local time) |
| `consumption_mw` | National consumption (DK1 + DK2 summed) |
| `temperature_2m`, `relativehumidity_2m`, `windspeed_10m` | Weather features |
| `hour`, `day_of_week`, `month` | Calendar features |
| `is_weekend` | 1 if Sat/Sun |
| `is_holiday_dk` | 1 if Danish public holiday |
| `consumption_lag_24h` | Consumption 24h earlier |
| `consumption_lag_48h` | Consumption 48h earlier |
| `consumption_lag_168h` | Consumption 1 week earlier |

## Troubleshooting

- **Error 429 (rate limit)** — Energi Data Service limits request frequency. Wait a few minutes and rerun.
- **Error 404** — The dataset may have been renamed. Check the catalog at `https://api.energidataservice.dk/meta/dataset`.
- **Missing lag values (NaN)** — The first 168 hours have no history, so `consumption_lag_*` are NaN. These rows can be dropped before training.