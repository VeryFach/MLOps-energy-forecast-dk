import logging
import time

import mlflow
import pandas as pd
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from energy_forecast.config import MLFLOW_TRACKING_URI, MODELS_DIR, PROCESSED_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Energy Forecast DK API",
    description="API for Denmark electricity consumption forecasting",
    version="0.2.0",
)

model = None
loaded_model_version = None
model_name = "energy-forecast-baseline"

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
PREDICTION_LATENCY = Gauge(
    "prediction_latency_ms",
    "Latest prediction latency in milliseconds",
)


class PredictionRequest(BaseModel):
    hours: int = 24


class PredictionResponse(BaseModel):
    datetime: list[str]
    consumption_mw: list[float]
    model_version: str
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str | None


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start
    endpoint = request.url.path
    REQUEST_LATENCY.labels(request.method, endpoint).observe(latency)
    REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()
    return response


def load_model():
    global model, loaded_model_version
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        versions = client.search_model_versions(f"name='{model_name}'")
        if versions:
            latest_version = max(versions, key=lambda v: int(v.version))
            model_uri = latest_version.source
            model = mlflow.sklearn.load_model(model_uri)
            loaded_model_version = latest_version.version
            logger.info(f"Loaded model {model_name} version {latest_version.version}")
            return latest_version.version
        else:
            logger.warning(
                "No model versions found in MLflow Registry. Using local fallback."
            )
            from joblib import load as joblib_load

            local_path = MODELS_DIR / "baseline_model.joblib"
            if local_path.exists():
                model = joblib_load(local_path)
                loaded_model_version = "local"
                logger.info(f"Loaded local model from {local_path}")
                return "local"
            raise FileNotFoundError("No model available")
    except Exception as e:
        logger.error(f"Failed to load model from MLflow: {e}")
        try:
            from joblib import load as joblib_load

            local_path = MODELS_DIR / "baseline_model.joblib"
            model = joblib_load(local_path)
            loaded_model_version = "local-fallback"
            logger.info(f"Fallback: loaded local model from {local_path}")
            return "local-fallback"
        except Exception as e2:
            logger.error(f"Local fallback also failed: {e2}")
            loaded_model_version = None
            return None


@app.on_event("startup")
async def startup_event():
    load_model()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy" if model is not None else "degraded",
        model_loaded=model is not None,
        model_version=load_model() if model is None else loaded_model_version,
    )


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    if model is None:
        load_model()
        if model is None:
            raise RuntimeError("Model not available")

    start = time.perf_counter()

    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    FEATURES = [
        "temperature_2m",
        "relativehumidity_2m",
        "windspeed_10m",
        "hour",
        "day_of_week",
        "month",
        "is_weekend",
        "is_holiday_dk",
        "consumption_lag_24h",
        "consumption_lag_48h",
        "consumption_lag_168h",
    ]

    last_ts = df["datetime"].iloc[-1]
    future = pd.date_range(
        start=last_ts + pd.Timedelta(hours=1), periods=request.hours, freq="h"
    )

    frame = pd.DataFrame(index=future)
    frame["hour"] = frame.index.hour
    frame["day_of_week"] = frame.index.dayofweek
    frame["month"] = frame.index.month
    frame["is_weekend"] = frame["day_of_week"].isin([5, 6]).astype(int)

    hist = df.set_index("datetime")["consumption_mw"]
    frame["consumption_lag_24h"] = hist.reindex(
        frame.index - pd.Timedelta(hours=24), method="ffill"
    ).values
    frame["consumption_lag_48h"] = hist.reindex(
        frame.index - pd.Timedelta(hours=48), method="ffill"
    ).values
    frame["consumption_lag_168h"] = hist.reindex(
        frame.index - pd.Timedelta(hours=168), method="ffill"
    ).values

    frame["temperature_2m"] = df["temperature_2m"].iloc[-1]
    frame["relativehumidity_2m"] = df["relativehumidity_2m"].iloc[-1]
    frame["windspeed_10m"] = df["windspeed_10m"].iloc[-1]
    frame["is_holiday_dk"] = 0

    predictions = model.predict(frame[FEATURES])
    latency = (time.perf_counter() - start) * 1000
    PREDICTION_LATENCY.set(latency)

    if latency > 5000:
        logger.warning(f"Prediction latency {latency:.0f}ms exceeds 5s threshold")

    return PredictionResponse(
        datetime=[dt.isoformat() for dt in future],
        consumption_mw=predictions.tolist(),
        model_version=loaded_model_version or "unknown",
        latency_ms=round(latency, 2),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
