import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_absolute_percentage_error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

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


def main():
    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    df = df.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)

    split_idx = int(len(df) * 0.8)
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]

    X_train, y_train = train[FEATURES], train[TARGET]
    X_test, y_test = test[FEATURES], test[TARGET]

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100

    print(f"Train rows: {len(train)}, Test rows: {len(test)}")
    print(f"Test range: {test['datetime'].min()} s/d {test['datetime'].max()}")
    print(f"RMSE: {rmse:.2f} MW")
    print(f"MAPE: {mape:.2f}%")
    print(f"MAE: {mean_absolute_error(y_test, y_pred):.2f} MW")


if __name__ == "__main__":
    main()