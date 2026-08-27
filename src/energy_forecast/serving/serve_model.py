import logging
import time

import mlflow
import numpy as np
import pandas as pd
from fastapi import FastAPI
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
model_name = "energy-forecast-baseline"


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


def load_model():
    global model
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        versions = client.search_model_versions(f"name='{model_name}'")
        if versions:
            latest_version = max(versions, key=lambda v: int(v.version))
            model_uri = latest_version.source
            model = mlflow.sklearn.load_model(model_uri)
            logger.info(f"Loaded model {model_name} version {latest_version.version}")
            return latest_version.version
        else:
            logger.warning("No model versions found in MLflow Registry. Using local fallback.")
            from joblib import load as joblib_load
            local_path = MODELS_DIR / "baseline_model.joblib"
            if local_path.exists():
                model = joblib_load(local_path)
                logger.info(f"Loaded local model from {local_path}")
                return "local"
            raise FileNotFoundError("No model available")
    except Exception as e:
        logger.error(f"Failed to load model from MLflow: {e}")
        try:
            from joblib import load as joblib_load
            local_path = MODELS_DIR / "baseline_model.joblib"
            model = joblib_load(local_path)
            logger.info(f"Fallback: loaded local model from {local_path}")
            return "local-fallback"
        except Exception as e2:
            logger.error(f"Local fallback also failed: {e2}")
            return None


@app.on_event("startup")
async def startup_event():
    load_model()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy" if model is not None else "degraded",
        model_loaded=model is not None,
        model_version=load_model() if model is None else "loaded",
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    global model
    if model is None:
        version = load_model()
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
    future = pd.date_range(start=last_ts + pd.Timedelta(hours=1), periods=request.hours, freq="h")

    frame = pd.DataFrame(index=future)
    frame["hour"] = frame.index.hour
    frame["day_of_week"] = frame.index.dayofweek
    frame["month"] = frame.index.month
    frame["is_weekend"] = frame["day_of_week"].isin([5, 6]).astype(int)

    hist = df.set_index("datetime")["consumption_mw"]
    frame["consumption_lag_24h"] = hist.reindex(frame.index - pd.Timedelta(hours=24), method="ffill").values
    frame["consumption_lag_48h"] = hist.reindex(frame.index - pd.Timedelta(hours=48), method="ffill").values
    frame["consumption_lag_168h"] = hist.reindex(frame.index - pd.Timedelta(hours=168), method="ffill").values

    frame["temperature_2m"] = df["temperature_2m"].iloc[-1]
    frame["relativehumidity_2m"] = df["relativehumidity_2m"].iloc[-1]
    frame["windspeed_10m"] = df["windspeed_10m"].iloc[-1]
    frame["is_holiday_dk"] = 0

    predictions = model.predict(frame[FEATURES])
    latency = (time.perf_counter() - start) * 1000

    if latency > 5000:
        logger.warning(f"Prediction latency {latency:.0f}ms exceeds 5s threshold")

    return PredictionResponse(
        datetime=[dt.isoformat() for dt in future],
        consumption_mw=predictions.tolist(),
        model_version="loaded",
        latency_ms=round(latency, 2),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
