# Energy Forecast DK — Documentation

This guide explains how to run the full data pipeline, serve predictions, and monitor the system.

## Overview

The project uses a standard MLOps `src/` layout. The Python package is `energy_forecast`, organized by responsibility:

```
src/energy_forecast/
├── config.py              # Parameters, paths, MinIO/MLflow config
├── data/                  # Ingestion, feature engineering & MinIO upload
│   ├── fetch_energy_dk.py
│   ├── fetch_weather.py
│   └── merge_data.py
├── models/                # Training with MLflow experiment tracking
│   ├── train_baseline.py
│   └── train_deep_learning.py
├── predict/               # Inference
│   └── predict_future.py
├── monitoring/            # Evaluation, drift detection & retraining trigger
│   ├── evaluate_model.py
│   ├── detect_drift.py
│   └── check_trigger.py
├── serving/               # FastAPI model serving
│   └── serve_model.py
└── orchestration/         # Pipeline runner
    ├── daily_pipeline.py
    └── prefect_flow.py
```

| Module | Purpose | Output |
|--------|---------|--------|
| `energy_forecast.data.fetch_energy_dk` | Download hourly electricity consumption (MW) for DK1 & DK2, upload to MinIO | `data/raw/consumption.csv` |
| `energy_forecast.data.fetch_weather` | Download hourly weather for Copenhagen | `data/raw/weather.csv` |
| `energy_forecast.data.merge_data` | Combine both datasets, add time/holiday/lag features, upload to MinIO | `data/processed/merged_data.csv` |
| `energy_forecast.monitoring.detect_drift` | Calculate 5 drift signals (PSI, night/day ratio, mean shift, peak shift, z-score) | `logs/drift_log.csv` |
| `energy_forecast.monitoring.evaluate_model` | Compute yesterday's MAPE and log it | `logs/mape_history.csv` |
| `energy_forecast.monitoring.check_trigger` | Retrain if MAPE > 5% OR drift signals exceeded | — |
| `energy_forecast.models.train_baseline` | Train RandomForest with MLflow tracking | MLflow Registry |
| `energy_forecast.models.train_deep_learning` | Train LSTM with MLflow tracking | MLflow Registry |
| `energy_forecast.serving.serve_model` | FastAPI serving layer for predictions | REST API |
| `energy_forecast.orchestration.daily_pipeline` | Run data scripts in sequence | — |
| `energy_forecast.orchestration.prefect_flow` | Prefect flow: pipeline + evaluate + trigger | — |

## Requirements

Install the package (from the project root):

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[deep-learning]"    # TensorFlow
pip install -e ".[serving]"          # FastAPI + uvicorn
pip install -e ".[airflow]"          # Apache Airflow
pip install -e ".[all]"              # All optional dependencies
```

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
Uploaded consumption.csv to MinIO bucket 'energy-forecast'
Saved 14328 records to ...\data\raw\weather.csv
Saved 5000 records to ...\data\processed\merged_data.csv
Uploaded merged_data.csv to MinIO bucket 'energy-forecast'
```

### Drift detection

Run the 5-signal drift detection to check for data drift:

```bash
python -m energy_forecast.monitoring.detect_drift
```

Signals monitored:

| Signal | Description | Threshold |
|--------|-------------|-----------|
| `peak_hour_psi` | Population Stability Index for peak hour consumption | PSI > 0.1 |
| `night_day_ratio` | Ratio of night (00-06) to day (10-16) consumption | Ratio > 1.5 or < 0.5 |
| `mean_consumption_shift` | Shift in mean consumption (last 7 days vs historical) | > 0.5 * std |
| `peak_hour_shift` | Shift in peak consumption hour | >= 2 hours |
| `consumption_zscore` | Z-score of last 24h mean vs historical | Z-score > 3.0 |

Results are saved to `logs/drift_log.csv`.

### Training with MLflow

Train the baseline model (RandomForest) with MLflow experiment tracking:

```bash
python -m energy_forecast.models.train_baseline
```

Train the deep learning model (LSTM) with MLflow experiment tracking:

```bash
python -m energy_forecast.models.train_deep_learning
```

Both scripts:
- Log parameters (model type, hyperparameters, train/test split)
- Log metrics (RMSE, MAPE)
- Register the model to the MLflow Registry
- Save locally to `models/`

View experiments at `http://localhost:5000`.

### Predicting the next 24 hours

After the pipeline has refreshed the data, forecast consumption for the next 24 hours:

```bash
python -m energy_forecast.predict.predict_future
```

This loads the trained baseline model (trains and caches it on first run), fetches the upcoming 24h weather forecast from Open-Meteo, builds the lag/calendar features, and prints the predicted hourly consumption.

### Model serving (FastAPI)

Start the prediction API server:

```bash
python -m uvicorn energy_forecast.serving.serve_model:app --host 0.0.0.0 --port 8000
```

API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (model status) |
| `POST` | `/predict` | Predict next N hours of consumption |

Example request:

```bash
curl -X POST "http://localhost:8000/predict" -H "Content-Type: application/json" -d '{"hours": 24}'
```

Swagger documentation: `http://localhost:8000/docs`

The server loads the model from the MLflow Registry (with local fallback).

### Monitoring & retraining

Evaluate the model against yesterday's actual data and log the MAPE:

```bash
python -m energy_forecast.monitoring.evaluate_model
```

Check whether the retraining trigger should fire:

```bash
python -m energy_forecast.monitoring.check_trigger
```

Retraining is triggered if:
- **MAPE > 5%** for 3 consecutive days, **OR**
- **Drift signals** exceed their thresholds (from `detect_drift.py`)

### Scheduled runs (Airflow)

The project includes an Apache Airflow DAG at `dags/energy_forecast_dag.py`.

DAG tasks:
1. `fetch_energy` — fetch consumption data
2. `fetch_weather` — fetch weather data
3. `merge_data` — feature engineering
4. `detect_drift` — run drift detection
5. `evaluate_model` — evaluate model performance
6. `check_and_retrain` — check triggers and retrain if needed

Schedule: daily at 01:00 (Europe/Copenhagen timezone).

Alternatively, use the Prefect flow:

```bash
python -m energy_forecast.orchestration.prefect_flow --serve
```

## Docker Deployment

Run the full MLOps stack with Docker Compose:

```bash
docker-compose up -d
```

This starts:
- **API** (port 8000) — FastAPI prediction service
- **MLflow** (port 5000) — experiment tracking & model registry
- **Prometheus** (port 9090) — metrics scraping
- **Grafana** (port 3000) — dashboards (login: admin/admin)

## How to update the CSV data

To fetch new/updated data, simply re-run the modules above. They overwrite the existing CSVs and upload to MinIO.

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
- **MinIO connection refused** — Ensure MinIO is running locally on port 9000.
- **MLflow connection refused** — Ensure MLflow server is running: `mlflow server --port 5000`.
