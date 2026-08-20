COUNTRY = "DK"
COUNTRY_NAME = "Denmark"
TIMEZONE = "Europe/Copenhagen"

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"

LATITUDE = 55.6761
LONGITUDE = 12.5683

ENERGIDATA_URL = "https://api.energidataservice.dk/v1/datastore_search"
ENERGIDATA_RESOURCE = "consumptionde35hour"
ENERGIDATA_DATASET_URL = "https://api.energidataservice.dk/dataset/GenerationProdTypeExchange"
ENERGIDATA_DATASET_NAME = "GenerationProdTypeExchange"
CONSUMPTION_FIELD = "GrossCon"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_VARIABLES = "temperature_2m,relativehumidity_2m,windspeed_10m"

HISTORY_START_DATE = "2026-01-01"
DATA_START_DATE = "2026-01-01"
FETCH_LIMIT = 10000

REFRESH_INTERVAL_MINUTES = 5