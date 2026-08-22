import mlflow
import mlflow.tensorflow
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.callbacks import ModelCheckpoint
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.models import Sequential

from energy_forecast.config import MODELS_DIR, MLFLOW_TRACKING_URI, PROCESSED_DIR

TARGET = "consumption_mw"
FEATURES = [
    "consumption_mw",
    "temperature_2m",
    "relativehumidity_2m",
    "windspeed_10m",
    "hour",
    "day_of_week",
    "month",
    "is_weekend",
    "is_holiday_dk",
]

WINDOW_SIZE = 24
EPOCHS = 50
BATCH_SIZE = 64
TRAIN_RATIO = 0.8


def make_sequences(data, window):
    X, y = [], []
    for i in range(len(data) - window):
        X.append(data[i : i + window])
        y.append(data[i + window, 0])
    return np.array(X), np.array(y)


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("energy-forecast-deep-learning")

    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.dropna(subset=FEATURES).reset_index(drop=True)

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(df[FEATURES])

    X, y = make_sequences(scaled, WINDOW_SIZE)

    split_idx = int(len(X) * TRAIN_RATIO)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    with mlflow.start_run(run_name="lstm-deep-learning"):
        mlflow.log_param("model_type", "LSTM")
        mlflow.log_param("window_size", WINDOW_SIZE)
        mlflow.log_param("epochs", EPOCHS)
        mlflow.log_param("batch_size", BATCH_SIZE)
        mlflow.log_param("n_features", len(FEATURES))
        mlflow.log_param("train_sequences", len(X_train))
        mlflow.log_param("test_sequences", len(X_test))
        mlflow.log_param("lstm_units", "64,32")
        mlflow.log_param("dropout_rate", 0.2)

        model = Sequential([
            LSTM(64, return_sequences=True, input_shape=(WINDOW_SIZE, len(FEATURES))),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(1),
        ])
        model.compile(optimizer="adam", loss="mse", metrics=["mae"])

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint = ModelCheckpoint(
            MODELS_DIR / "lstm_model.keras",
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        )

        model.fit(
            X_train,
            y_train,
            epochs=EPOCHS,
            batch_size=BATCH_SIZE,
            validation_data=(X_test, y_test),
            callbacks=[checkpoint],
            verbose=1,
        )

        y_pred = model.predict(X_test)
        y_test_inv = scaler.inverse_transform(
            np.hstack([y_test.reshape(-1, 1), np.zeros((len(y_test), len(FEATURES) - 1))])
        )[:, 0]
        y_pred_inv = scaler.inverse_transform(
            np.hstack([y_pred, np.zeros((len(y_pred), len(FEATURES) - 1))])
        )[:, 0]

        rmse = float(np.sqrt(np.mean((y_test_inv - y_pred_inv) ** 2)))
        mape = float(np.mean(np.abs((y_test_inv - y_pred_inv) / y_test_inv)) * 100)

        mlflow.log_metric("rmse", rmse)
        mlflow.log_metric("mape", mape)

        mlflow.tensorflow.log_model(
            tf_model=model,
            artifact_path="model",
            registered_model_name="energy-forecast-lstm",
        )

        print(f"Train sequences: {len(X_train)}, Test sequences: {len(X_test)}")
        print(f"RMSE: {rmse:.2f} MW")
        print(f"MAPE: {mape:.2f}%")
        print(f"Best model saved to {MODELS_DIR / 'lstm_model.keras'}")
        print(f"MLflow run logged successfully.")


if __name__ == "__main__":
    main()
