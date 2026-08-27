import mlflow
import mlflow.sklearn
import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
)

from energy_forecast.config import MLFLOW_TRACKING_URI, MODELS_DIR, PROCESSED_DIR

MODEL_PATH = MODELS_DIR / "baseline_model.joblib"

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
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("energy-forecast-baseline")

    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)

    split_idx = int(len(df) * 0.8)
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]

    X_train, y_train = train[FEATURES], train[TARGET]
    X_test, y_test = test[FEATURES], test[TARGET]

    with mlflow.start_run(run_name="random-forest-baseline"):
        mlflow.log_param("model_type", "RandomForestRegressor")
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.log_param("n_features", len(FEATURES))

        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        rmse = mean_squared_error(y_test, y_pred) ** 0.5
        mape = mean_absolute_percentage_error(y_test, y_pred) * 100
        mae = mean_absolute_error(y_test, y_pred)

        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mape", mape)
        mlflow.log_metric("mae", mae)

        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name="energy-forecast-baseline",
        )

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        dump(model, MODEL_PATH)

        print(f"Train rows: {len(train)}, Test rows: {len(test)}")
        print(f"Test range: {test['datetime'].min()} to {test['datetime'].max()}")
        print(f"RMSE: {rmse:.2f} MW")
        print(f"MAPE: {mape:.2f}%")
        print(f"MAE: {mae:.2f} MW")
        print(f"Model saved to {MODEL_PATH}")
        print("MLflow run logged successfully.")


if __name__ == "__main__":
    main()
