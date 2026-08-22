import pandas as pd
from joblib import load

from energy_forecast.config import PROCESSED_DIR, MODELS_DIR, LOGS_DIR

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
MAPE_HISTORY_PATH = LOGS_DIR / "mape_history.csv"


def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model tidak ditemukan: {MODEL_PATH}. Jalankan predict_future.py atau train_baseline.py dulu.")
    return load(MODEL_PATH)


def evaluate_last_day(df):
    df = df.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)

    last_ts = df["datetime"].iloc[-1]
    yesterday = df[df["datetime"] > last_ts - pd.Timedelta(hours=24)]

    if len(yesterday) < 24:
        print(f"Peringatan: hanya {len(yesterday)} jam data aktual, gunakan yang tersedia.")

    model = load_model()
    y_pred = model.predict(yesterday[FEATURES])
    y_true = yesterday[TARGET].values

    mape = float((abs(y_true - y_pred) / y_true).mean() * 100)
    eval_date = yesterday["datetime"].iloc[-1].date().isoformat()
    return eval_date, mape, len(yesterday)


def append_mape(eval_date, mape, n_hours):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    row = pd.DataFrame({"date": [eval_date], "mape": [round(mape, 2)], "n_hours": [n_hours]})
    if MAPE_HISTORY_PATH.exists():
        history = pd.read_csv(MAPE_HISTORY_PATH)
        history = history[history["date"] != eval_date]
        history = pd.concat([history, row], ignore_index=True)
    else:
        history = row
    history.to_csv(MAPE_HISTORY_PATH, index=False)
    return MAPE_HISTORY_PATH


def main():
    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    eval_date, mape, n_hours = evaluate_last_day(df)
    path = append_mape(eval_date, mape, n_hours)

    print(f"MAPE {eval_date} ({n_hours} jam): {mape:.2f}%")
    print(f"Disimpan ke {path}")


if __name__ == "__main__":
    main()