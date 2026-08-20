import time
import requests
import pandas as pd
import holidays
from sklearn.ensemble import RandomForestRegressor
from joblib import dump, load

from energy_forecast.config import (
    LATITUDE,
    LONGITUDE,
    OPEN_METEO_URL,
    OPEN_METEO_ARCHIVE_URL,
    WEATHER_VARIABLES,
    TIMEZONE,
    PROCESSED_DIR,
    MODELS_DIR,
)

TARGET = "consumption_mw"
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
MODEL_PATH = MODELS_DIR / "baseline_model.joblib"


def load_model():
    if MODEL_PATH.exists():
        return load(MODEL_PATH)

    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(df[FEATURES], df[TARGET])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dump(model, MODEL_PATH)
    return model


def fetch_weather(start_ts, end_ts):
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start_ts.date().isoformat(),
        "end_date": end_ts.date().isoformat(),
        "hourly": WEATHER_VARIABLES,
        "timezone": TIMEZONE,
    }
    now_local = pd.Timestamp.now(tz="UTC").tz_convert(TIMEZONE).tz_localize(None)
    url = OPEN_METEO_URL if start_ts > now_local else OPEN_METEO_ARCHIVE_URL
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return pd.DataFrame(response.json()["hourly"])


def predict_future(hours=24):
    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    model = load_model()

    last_ts = df["datetime"].iloc[-1]
    future = pd.date_range(start=last_ts + pd.Timedelta(hours=1), periods=hours, freq="h")

    weather = fetch_weather(future[0], future[-1])
    weather["datetime"] = pd.to_datetime(weather["time"])
    weather = weather.set_index("datetime")[["temperature_2m", "relativehumidity_2m", "windspeed_10m"]]

    hist = df.set_index("datetime")["consumption_mw"]

    frame = pd.DataFrame(index=future)
    frame["temperature_2m"] = weather["temperature_2m"].reindex(future).values
    frame["relativehumidity_2m"] = weather["relativehumidity_2m"].reindex(future).values
    frame["windspeed_10m"] = weather["windspeed_10m"].reindex(future).values

    frame["hour"] = frame.index.hour
    frame["day_of_week"] = frame.index.dayofweek
    frame["month"] = frame.index.month
    frame["is_weekend"] = frame["day_of_week"].isin([5, 6]).astype(int)

    dk_holidays = holidays.Denmark(years=range(frame.index.year.min(), frame.index.year.max() + 1))
    frame["is_holiday_dk"] = pd.Series(frame.index.date).isin(dk_holidays).astype(int).values

    frame["consumption_lag_24h"] = hist.reindex(frame.index - pd.Timedelta(hours=24), method="ffill").values
    frame["consumption_lag_48h"] = hist.reindex(frame.index - pd.Timedelta(hours=48), method="ffill").values
    frame["consumption_lag_168h"] = hist.reindex(frame.index - pd.Timedelta(hours=168), method="ffill").values

    pred = model.predict(frame[FEATURES])

    result = pd.DataFrame({
        "datetime": frame.index,
        "consumption_mw": pred,
    })
    return result


def main():
    start = time.perf_counter()
    result = predict_future(hours=24)
    elapsed = time.perf_counter() - start

    print(f"Prediksi 24 jam ke depan (berdasarkan data terakhir {result['datetime'].iloc[0] - pd.Timedelta(hours=1)}):")
    print(result.to_string(index=False))
    print(f"Waktu eksekusi: {elapsed:.2f} detik")
    assert elapsed < 5, "Waktu eksekusi melebihi 5 detik!"


if __name__ == "__main__":
    main()