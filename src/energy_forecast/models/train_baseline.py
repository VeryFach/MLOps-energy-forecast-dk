import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import mlflow
import mlflow.sklearn
import pandas as pd
from joblib import dump
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient
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


def train_once(
    n_estimators=100, max_depth=None, min_samples_leaf=1, data_path=None, register=False
):
    data_path = data_path or PROCESSED_DIR / "merged_data.csv"
    if not data_path.is_file():
        raise FileNotFoundError(
            f"Dataset tidak ditemukan: {data_path}. Jalankan python src/preprocess.py dahulu."
        )
    data_hash = hashlib.md5(data_path.read_bytes()).hexdigest()
    df = pd.read_csv(data_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.dropna(subset=FEATURES + [TARGET]).reset_index(drop=True)
    if len(df) < 10:
        raise ValueError(
            "Dataset terlalu kecil setelah membuang baris tanpa fitur/target."
        )

    split_idx = int(len(df) * 0.8)
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]

    X_train, y_train = train[FEATURES], train[TARGET]
    X_test, y_test = test[FEATURES], test[TARGET]

    run_name = f"rf-n{n_estimators}-depth{max_depth or 'none'}-leaf{min_samples_leaf}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_param("model_type", "RandomForestRegressor")
        mlflow.log_param("n_estimators", n_estimators)
        mlflow.log_param("max_depth", max_depth if max_depth is not None else "None")
        mlflow.log_param("min_samples_leaf", min_samples_leaf)
        mlflow.log_param("random_state", 42)
        mlflow.log_param("data_md5", data_hash)
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.log_param("n_features", len(FEATURES))

        model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        rmse = mean_squared_error(y_test, y_pred) ** 0.5
        mape = mean_absolute_percentage_error(y_test, y_pred) * 100
        mae = mean_absolute_error(y_test, y_pred)

        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mape", mape)
        mlflow.log_metric("mae", mae)

        try:
            model_info = mlflow.sklearn.log_model(
                sk_model=model,
                name="model",
                skops_trusted_types=["sklearn.tree._tree.Tree"],
            )
            model_uri = model_info.model_uri
        except MlflowException as exc:
            if "logged-models" not in str(exc) or "404" not in str(exc):
                raise
            # MLflow 2.x servers lack the logged-model endpoint used by 3.x clients.
            # Save the MLflow model and upload it as a run artifact instead.
            with TemporaryDirectory() as temp_dir:
                model_dir = Path(temp_dir) / "model"
                mlflow.sklearn.save_model(
                    model,
                    path=str(model_dir),
                    skops_trusted_types=["sklearn.tree._tree.Tree"],
                )
                mlflow.log_artifacts(str(model_dir), artifact_path="model")
            model_uri = f"runs:/{run.info.run_id}/model"
        if register:
            registered = mlflow.register_model(model_uri, "energy-forecast-baseline")
            client = MlflowClient()
            client.transition_model_version_stage(
                name="energy-forecast-baseline",
                version=registered.version,
                stage="Production",
                archive_existing_versions=True,
            )
            client.set_registered_model_alias(
                "energy-forecast-baseline", "champion", registered.version
            )
            print(
                f"Model version {registered.version} promoted to Production",
                flush=True,
            )

        if register:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            dump(model, MODEL_PATH)

        print(f"Train rows: {len(train)}, Test rows: {len(test)}")
        print(f"Test range: {test['datetime'].min()} to {test['datetime'].max()}")
        print(f"RMSE: {rmse:.2f} MW")
        print(f"MAPE: {mape:.2f}%")
        print(f"MAE: {mae:.2f} MW")
        if register:
            print(f"Model saved to {MODEL_PATH}")
        print(f"MLflow run: {run.info.run_id}")
        return {
            "run_id": run.info.run_id,
            "rmse": rmse,
            "mae": mae,
            "mape": mape,
            "model_uri": model_uri,
            "data_md5": data_hash,
            "params": {
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "min_samples_leaf": min_samples_leaf,
                "random_state": 42,
            },
        }


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("energy-forecast-baseline")
    train_once(register=True)


if __name__ == "__main__":
    main()
