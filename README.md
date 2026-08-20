# Energy Forecast DK

Predict electricity consumption (MW) in Denmark using hourly time-series data from the Energi Data Service and weather data from the Open-Meteo API. The goal is to help grid operators and energy providers prevent energy waste and blackouts.

## Architecture

```
energy-forecast-dk/
├── src/energy_forecast/     # Python package (installable via pip install -e .)
│   ├── config.py            # Parameters: country, coordinates, API URLs, start date, paths
│   ├── data/                # Ingestion & feature engineering
│   │   ├── fetch_energy_dk.py
│   │   ├── fetch_weather.py
│   │   └── merge_data.py
│   ├── models/              # Training
│   │   ├── train_baseline.py
│   │   └── train_deep_learning.py
│   ├── predict/             # Inference
│   │   └── predict_future.py
│   ├── monitoring/          # Evaluation & retraining trigger
│   │   ├── evaluate_model.py
│   │   └── check_trigger.py
│   └── orchestration/       # Pipeline runner & scheduling
│       ├── daily_pipeline.py
│       └── prefect_flow.py
├── data/
│   ├── raw/                 # Raw data (git-ignored, created by the scripts)
│   └── processed/           # Merged feature table (git-ignored)
├── models/                  # Trained models (git-ignored)
├── logs/                    # Monitoring logs (git-ignored)
├── docs/
│   └── README.md            # Pipeline & usage documentation
├── pyproject.toml
├── .gitignore
└── README.md
```

## Data Sources

| Source | Data | API Key |
|--------|------|---------|
| [Energi Data Service](https://www.energidataservice.dk/) | Hourly electricity consumption (MW) | None |
| [Open-Meteo](https://open-meteo.com/) | Weather: temperature, humidity, wind | None |

> Note: The legacy `ConsumptionDE35` dataset is no longer available. The script uses `GenerationProdTypeExchange` (column `GrossCon` = gross consumption in MW) for DK1 and DK2.

## Prerequisites

- Python 3.10+
- [Git](https://git-scm.com/)
- Internet access (to reach the APIs)

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

Optional extras: `pip install -e ".[deep-learning,prefect]"`.

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

1. Call the Energi Data Service API with the `start` parameter (from `config.py`) and `limit=10000`.
2. Convert the JSON response into a pandas DataFrame.
3. Save the result to `data/raw/consumption.csv`.

Expected output:

```
Saved 10000 records to D:\...\energy-forecast-dk\data\raw\consumption.csv
```

Structure of `data/raw/consumption.csv`:

| Column | Description |
|--------|-------------|
| `TimeUTC` | Timestamp in UTC |
| `TimeDK` | Danish local time |
| `PriceArea` | Price area: DK1 (West) / DK2 (East) |
| `ConsumptionMW` | Electricity consumption in MW |

### Predicting the next 24 hours

```bash
python -m energy_forecast.predict.predict_future
```

Trains/caches a baseline model, fetches the 24h weather forecast, and prints the predicted hourly consumption. See `docs/README.md` for details.

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
| `REFRESH_INTERVAL_MINUTES` | Update interval (near-real-time) | `5` |

## MLOps Pipeline

1. **Ingestion** — `energy_forecast.data.fetch_energy_dk` downloads raw consumption data.
2. **Weather ingestion** — `energy_forecast.data.fetch_weather` downloads weather data from Open-Meteo.
3. **Feature engineering** — `energy_forecast.data.merge_data` combines both, adding time/holiday/lag features.
4. **Daily orchestration** — `energy_forecast.orchestration.daily_pipeline` runs steps 1–3 in sequence.
5. **Training** — `energy_forecast.models.train_baseline` / `train_deep_learning` train forecasting models.
6. **Prediction** — `energy_forecast.predict.predict_future` forecasts the next 24h using the latest data.
7. **Monitoring** — `energy_forecast.monitoring.evaluate_model` + `check_trigger` detect drift and auto-retrain.

## Troubleshooting

**Error 429 (Rate limit)** — Energi Data Service limits request frequency. Wait a few minutes and rerun.

**Error 404** — The dataset may have been renamed or removed. Check the dataset catalog at `https://api.energidataservice.dk/meta/dataset`.