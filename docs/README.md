# Energy Forecast DK — Documentation

This guide explains how to run the full data pipeline and how to refresh the CSV data files.

## Overview

The project uses a standard MLOps `src/` layout. The Python package is `energy_forecast`, organized by responsibility:

```
src/energy_forecast/
├── config.py          # Parameters & shared paths
├── data/              # Ingestion & feature engineering
│   ├── fetch_energy_dk.py
│   ├── fetch_weather.py
│   └── merge_data.py
├── models/            # Training
│   ├── train_baseline.py
│   └── train_deep_learning.py
├── predict/           # Inference
│   └── predict_future.py
├── monitoring/        # Evaluation & retraining trigger
│   ├── evaluate_model.py
│   └── check_trigger.py
└── orchestration/     # Pipeline runner & scheduling
    ├── daily_pipeline.py
    └── prefect_flow.py
```

| Module | Purpose | Output |
|--------|---------|--------|
| `energy_forecast.data.fetch_energy_dk` | Download hourly electricity consumption (MW) for DK1 & DK2 | `data/raw/consumption.csv` |
| `energy_forecast.data.fetch_weather` | Download hourly weather for Copenhagen | `data/raw/weather.csv` |
| `energy_forecast.data.merge_data` | Combine both datasets, add time/holiday/lag features | `data/processed/merged_data.csv` |
| `energy_forecast.orchestration.daily_pipeline` | Run the three data scripts in sequence (fetch → fetch → merge) | — |
| `energy_forecast.predict.predict_future` | Predict the next 24h of consumption from the latest data | console output |
| `energy_forecast.monitoring.evaluate_model` | Compute yesterday's MAPE and log it | `logs/mape_history.csv` |
| `energy_forecast.monitoring.check_trigger` | Retrain if MAPE > 5% for 3 consecutive days | — |
| `energy_forecast.orchestration.prefect_flow` | Prefect flow: pipeline + evaluate + trigger | — |

## Requirements

Install the package (from the project root):

```bash
pip install -e .
```

Optional extras: `pip install -e ".[deep-learning,prefect]"`.

## Running the pipeline

Run the modules in order. From the project root:

```bash
python -m energy_forecast.data.fetch_energy_dk
python -m energy_forecast.data.fetch_weather
python -m energy_forecast.data.merge_data
```

Or run everything at once with the orchestrator:

```bash
python -m energy_forecast.orchestration.daily_pipeline
```

It executes the three scripts sequentially and stops if any of them fails (non-zero exit code).

Expected output:

```
Saved 10000 records to ...\data\raw\consumption.csv
Saved 14328 records to ...\data\raw\weather.csv
Saved 5000 records to ...\data\processed\merged_data.csv
```

### Predicting the next 24 hours

After the pipeline has refreshed the data, forecast consumption for the next 24 hours:

```bash
python -m energy_forecast.predict.predict_future
```

This loads the trained baseline model (trains and caches it to `models/baseline_model.joblib` on first run), fetches the upcoming 24h weather forecast from Open-Meteo, builds the lag/calendar features from the latest history, and prints the predicted hourly consumption. Execution completes in well under 5 seconds.

### Monitoring & retraining

Evaluate the model against yesterday's actual data and log the MAPE:

```bash
python -m energy_forecast.monitoring.evaluate_model
```

Check whether the retraining trigger should fire (MAPE > 5% for 3 consecutive days → reruns `train_baseline`):

```bash
python -m energy_forecast.monitoring.check_trigger
```

### Scheduled runs (Prefect)

The Prefect flow wraps pipeline → evaluate → trigger and can serve itself with a daily cron at 01:00:

```bash
python -m energy_forecast.orchestration.prefect_flow --serve
```

Alternatively, register the Windows Task Scheduler task that runs the daily pipeline at 01:00:

```bash
python -m energy_forecast.orchestration.daily_pipeline --setup-task
```

## How to update the CSV data

To fetch new/updated data, simply re-run the modules above. They overwrite the existing CSVs.

- **Consumption** — fetches records from `DATA_START_DATE` up to `FETCH_LIMIT` records, so newer data is included on each run.
- **Weather** — always fetches from `HISTORY_START_DATE` to *today* (`end_date = today`), so re-running captures the latest days.
- **Merged** — rebuilds the feature table from the two raw CSVs.

### Configuring the data window

All parameters live in `src/energy_forecast/config.py`:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_START_DATE` | Start date for consumption fetch | `2026-01-01` |
| `HISTORY_START_DATE` | Start date for weather fetch | `2026-01-01` |
| `FETCH_LIMIT` | Max records from Energi Data Service | `10000` |

### Update procedure

1. (Optional) Change the date range in `src/energy_forecast/config.py`.
2. Run the fetch modules, then the merge module:

```bash
python -m energy_forecast.data.fetch_energy_dk
python -m energy_forecast.data.fetch_weather
python -m energy_forecast.data.merge_data
```

or just:

```bash
python -m energy_forecast.orchestration.daily_pipeline
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
- **`ModuleNotFoundError: energy_forecast`** — reinstall the package: `pip install -e .`