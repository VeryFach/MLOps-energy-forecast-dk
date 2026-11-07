"""Run three comparable Random Forest experiments and register the best one."""

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from joblib import dump
from mlflow.tracking import MlflowClient

from energy_forecast.config import (
    MLFLOW_TRACKING_URI,
    MODELS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from energy_forecast.data.merge_data import (
    add_holiday_feature,
    add_lag_features,
    add_time_features,
    clean_missing_values,
    load_consumption,
    load_weather,
)
from energy_forecast.models.train_baseline import train_once

EXPERIMENT = "energy-forecast-baseline"
REGISTERED_MODEL = "energy-forecast-baseline"
VARIANTS = [
    {"n_estimators": 50, "max_depth": 8, "min_samples_leaf": 2},
    {"n_estimators": 120, "max_depth": 16, "min_samples_leaf": 1},
    {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 1},
]


def dvc_raw_versions():
    """Verify the checked-out raw files match the LK-05 DVC pointers."""
    versions = {}
    for name in ("consumption", "weather"):
        raw = RAW_DIR / f"{name}.csv"
        pointer = RAW_DIR / f"{name}.csv.dvc"
        if not raw.is_file() or not pointer.is_file():
            raise FileNotFoundError(
                f"Dataset DVC {name} belum tersedia; jalankan dvc pull."
            )
        match = re.search(r"(?m)^\s*-\s*md5:\s*([0-9a-f]{32})\s*$", pointer.read_text())
        if not match:
            raise ValueError(f"Pointer DVC tidak valid: {pointer}")
        actual = hashlib.md5(raw.read_bytes()).hexdigest()
        if actual != match.group(1):
            raise ValueError(f"Hash {raw} berbeda dari {pointer}; jalankan dvc pull.")
        versions[f"{name}_dvc_md5"] = actual
    return versions


def verify_processed_dataset(data_path):
    """Reject a stale feature table when using the default LK-05 dataset."""
    if data_path.resolve() != (PROCESSED_DIR / "merged_data.csv").resolve():
        return
    if not data_path.is_file():
        raise FileNotFoundError(
            f"{data_path} belum ada; jalankan python src/preprocess.py."
        )
    merged = pd.merge(load_consumption(), load_weather(), on="datetime", how="inner")
    merged = clean_missing_values(
        add_lag_features(add_holiday_feature(add_time_features(merged)))
    )
    expected = hashlib.md5(merged.to_csv(index=False).encode()).hexdigest()
    actual = hashlib.md5(data_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            "Dataset processed tidak cocok dengan raw DVC; jalankan python src/preprocess.py."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default=MLFLOW_TRACKING_URI)
    parser.add_argument("--data", type=Path, default=PROCESSED_DIR / "merged_data.csv")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs")
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Leave registration to the validation gate",
    )
    args = parser.parse_args()

    versions = dvc_raw_versions()
    verify_processed_dataset(args.data)
    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    client = MlflowClient()
    results = []
    for params in VARIANTS:
        result = train_once(data_path=args.data, **params)
        for key, value in versions.items():
            client.log_param(result["run_id"], key, value)
        results.append(result)

    best = min(results, key=lambda item: item["rmse"])
    version = (
        None
        if args.no_register
        else mlflow.register_model(best["model_uri"], REGISTERED_MODEL)
    )
    best_model = mlflow.sklearn.load_model(best["model_uri"])
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dump(best_model, MODELS_DIR / "baseline_model.joblib")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "best_run.json").write_text(
        json.dumps(
            {"experiment": EXPERIMENT, "model_name": REGISTERED_MODEL, **best}, indent=2
        ),
        encoding="utf-8",
    )
    csv_path = args.output_dir / "experiment_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_id",
                "n_estimators",
                "max_depth",
                "min_samples_leaf",
                "rmse",
                "mae",
                "mape",
                "data_md5",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "run_id": result["run_id"],
                    **{
                        key: result["params"][key]
                        for key in ("n_estimators", "max_depth", "min_samples_leaf")
                    },
                    **{key: result[key] for key in ("rmse", "mae", "mape", "data_md5")},
                }
            )

    metadata = args.output_dir / "model_metadata.md"
    metadata.write_text(
        "# Metadata model terpilih\n\n"
        f"- Eksperimen: `{EXPERIMENT}`\n"
        f"- MLflow tracking URI: `{args.tracking_uri}`\n"
        f"- Run ID: `{best['run_id']}`\n"
        f"- Model Registry: `{REGISTERED_MODEL}` versi `{version.version if version else 'menunggu validasi'}`\n"
        f"- Model URI: `{best['model_uri']}`\n"
        f"- Parameter: `{best['params']}`\n"
        f"- RMSE: `{best['rmse']:.4f}` MW; MAE: `{best['mae']:.4f}` MW; "
        f"MAPE: `{best['mape']:.4f}`%\n"
        f"- Processed dataset MD5: `{best['data_md5']}`\n"
        + "".join(f"- {key}: `{value}`\n" for key, value in versions.items())
        + "- Pemilihan: RMSE terendah pada 20% data uji paling akhir (split kronologis).\n",
        encoding="utf-8",
    )
    print(f"Model terbaik: run {best['run_id']} (RMSE {best['rmse']:.4f} MW)")
    if version:
        print(f"Terdaftar sebagai {REGISTERED_MODEL} versi {version.version}")
    else:
        print("Registrasi ditunda sampai validasi berhasil")
    print(f"Ringkasan: {csv_path}; metadata: {metadata}")


if __name__ == "__main__":
    main()
