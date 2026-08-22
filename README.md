# Energy Forecast DK

Predict electricity consumption (MW) in Denmark using hourly time-series data from the Energi Data Service and weather data from the Open-Meteo API. The goal is to help grid operators and energy providers prevent energy waste and blackouts.

## Architecture

```
energy-forecast-dk/
├── src/energy_forecast/          # Python package (installable via pip install -e .)
│   ├── config.py                 # Parameters: country, coordinates, API URLs, paths, MinIO/MLflow config
│   ├── data/                     # Ingestion, feature engineering & MinIO upload
│   │   ├── fetch_energy_dk.py
│   │   ├── fetch_weather.py
│   │   └── merge_data.py
│   ├── models/                   # Training with MLflow tracking
│   │   ├── train_baseline.py
│   │   └── train_deep_learning.py
│   ├── predict/                  # Inference
│   │   └── predict_future.py
│   ├── monitoring/               # Evaluation, drift detection & retraining trigger
│   │   ├── evaluate_model.py
│   │   ├── detect_drift.py
│   │   └── check_trigger.py
│   ├── serving/                  # FastAPI model serving
│   │   └── serve_model.py
│   └── orchestration/            # Pipeline runner
│       ├── daily_pipeline.py
│       └── prefect_flow.py
├── dags/                         # Apache Airflow DAGs
│   └── energy_forecast_dag.py
├── monitoring/                   # Prometheus & Grafana configuration
│   ├── prometheus.yml
│   └── grafana/
├── data/
│   ├── raw/                      # Raw data (git-ignored, created by the scripts)
│   └── processed/                # Merged feature table (git-ignored)
├── models/                       # Trained models (git-ignored)
├── logs/                         # Monitoring & drift logs (git-ignored)
├── docs/
│   └── README.md                 # Detailed pipeline & usage documentation
├── Dockerfile                    # API container image
├── docker-compose.yml            # Full stack: API, MLflow, Prometheus, Grafana
├── pyproject.toml
├── .gitignore
└── README.md
```

## Data Sources

| Source | Data | API Key |
|--------|------|---------|
| [Energi Data Service](https://www.energidataservice.dk/) | Hourly electricity consumption (MW) | None |
| [Open-Meteo](https://open-meteo.com/) | Weather: temperature, humidity, wind | None |

## Prerequisites

- Python 3.10+
- [Git](https://git-scm.com/)
- Internet access (to reach the APIs)
- Docker & Docker Compose (for full MLOps stack)
- MinIO running locally on port 9000 (for object storage)
- Apache Airflow (for DAG-based orchestration)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/VeryFach/energy-forecast-dk.git
cd energy-forecast-dk
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate the environment:

- **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Linux/macOS:**
  ```bash
  source .venv/bin/activate
  ```

### 3. Install dependencies

```bash
pip install -e .
```

Optional extras:

```bash
# Deep learning (TensorFlow)
pip install -e ".[deep-learning]"

# FastAPI serving
pip install -e ".[serving]"

# Apache Airflow
pip install -e ".[airflow]"

# All optional dependencies
pip install -e ".[all]"
```

## Running

### Daily data pipeline

Fetch new data and rebuild the feature table with one command:

```bash
python -m energy_forecast.orchestration.daily_pipeline
```

This runs, in order: `fetch_energy_dk` → `fetch_weather` → `merge_data`. Each step can also be run individually:

```bash
python -m energy_forecast.data.fetch_energy_dk
python -m energy_forecast.data.fetch_weather
python -m energy_forecast.data.merge_data
```

Data is saved locally to `data/raw/` and `data/processed/`, and also uploaded to **MinIO** object storage.

### Drift detection

Run the 5-signal drift detection:

```bash
python -m energy_forecast.monitoring.detect_drift
```

Signals: PSI (peak hours), night/day ratio, mean consumption shift, peak hour shift, z-score.

### Training with MLflow

```bash
python -m energy_forecast.models.train_baseline
python -m energy_forecast.models.train_deep_learning
```

Both scripts log metrics (RMSE, MAPE) and register models to the **MLflow Registry**.

### Model serving (FastAPI)

```bash
python -m uvicorn energy_forecast.serving.serve_model:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /health` — health check
- `POST /predict` — predict next N hours of consumption

Swagger docs available at `http://localhost:8000/docs`.

### Scheduled runs (Airflow)

Place the DAG file at `dags/energy_forecast_dag.py` and trigger via Airflow UI or CLI:

```bash
airflow dags list
airflow dags test energy_forecast_daily
```

## Docker Deployment

Run the full MLOps stack (API + MLflow + Prometheus + Grafana):

```bash
docker-compose up -d
```

Services:
| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI prediction service |
| MLflow | 5000 | Experiment tracking & model registry |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3000 | Dashboards (admin/admin) |

## Configuration

All parameters live in `src/energy_forecast/config.py`:

| Variable | Description | Default |
|----------|-------------|---------|
| `COUNTRY` | Country code | `DK` |
| `TIMEZONE` | Timezone | `Europe/Copenhagen` |
| `LATITUDE`, `LONGITUDE` | Coordinates for weather | `55.6761`, `12.5683` |
| `ENERGIDATA_DATASET_URL` | Energi Data Service API URL | ... |
| `DATA_START_DATE` | Start date for fetching data | `2026-01-01` |
| `FETCH_LIMIT` | Maximum number of records | `10000` |
| `MINIO_ENDPOINT` | MinIO object storage URL | `http://localhost:9000` |
| `MLFLOW_TRACKING_URI` | MLflow tracking server URL | `http://localhost:5000` |

## MLOps Pipeline

1. **Ingestion** — `energy_forecast.data.fetch_energy_dk` downloads raw consumption data and uploads to MinIO.
2. **Weather ingestion** — `energy_forecast.data.fetch_weather` downloads weather data from Open-Meteo.
3. **Feature engineering** — `energy_forecast.data.merge_data` combines both, adds time/holiday/lag features, uploads to MinIO.
4. **Drift detection** — `energy_forecast.monitoring.detect_drift` calculates 5 drift signals.
5. **Daily orchestration** — `energy_forecast.orchestration.daily_pipeline` or **Airflow DAG** runs the full pipeline.
6. **Training** — `energy_forecast.models.train_baseline` / `train_deep_learning` train models with MLflow tracking.
7. **Prediction** — `energy_forecast.predict.predict_future` forecasts the next 24h.
8. **Monitoring** — `evaluate_model` + `check_trigger` detect drift and auto-retrain (MAPE > 5% OR drift signals exceeded).
9. **Serving** — FastAPI serves predictions via REST API, containerized with Docker.

## Troubleshooting

**Error 429 (Rate limit)** — Energi Data Service limits request frequency. Wait a few minutes and rerun.

**Error 404** — The dataset may have been renamed or removed. Check the dataset catalog at `https://api.energidataservice.dk/meta/dataset`.

**MinIO connection refused** — Ensure MinIO is running locally on port 9000.

**MLflow connection refused** — Ensure MLflow server is running: `mlflow server --port 5000`.
