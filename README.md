# Energy Forecast DK

Predict electricity consumption (MW) in Denmark using hourly time-series data from the Energi Data Service and weather data from the Open-Meteo API. The goal is to help grid operators and energy providers prevent energy waste and blackouts.

## Architecture

```
energy-forecast-dk/
├── app/
│   ├── config.py            # Parameters: country, coordinates, API URLs, start date
│   └── fetch_energy_dk.py   # Fetch electricity consumption data & save to CSV
├── data/
│   └── raw/                 # Raw data (git-ignored, created by the script)
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
pip install requests pandas
```

## Running

### Fetch electricity consumption data

```bash
python app/fetch_energy_dk.py
```

This script will:
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

### (Upcoming) Fetch weather data

A `fetch_weather_dk.py` script will use `OPEN_METEO_URL` in `config.py` to fetch historical weather data based on `LATITUDE`/`LONGITUDE`.

## Configuration

All parameters live in `app/config.py`:

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

1. **Ingestion** — `fetch_energy_dk.py` downloads raw data (current).
2. **Weather ingestion** — fetch weather data from Open-Meteo (planned).
3. **Feature engineering** — combine consumption + weather, create time features (hour, day, season).
4. **Training** — train a time-series forecasting model (regression).
5. **Monitoring** — detect data drift (seasonality, holidays, regulation).

## Troubleshooting

**Error 429 (Rate limit)** — Energi Data Service limits request frequency. Wait a few minutes and rerun.

**Error 404** — The dataset may have been renamed or removed. Check the dataset catalog at `https://api.energidataservice.dk/meta/dataset`.