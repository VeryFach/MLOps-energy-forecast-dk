"""Validation gate and Staging registration for code-triggered training."""

import argparse
import json
import math
import os
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

from energy_forecast.config import MLFLOW_TRACKING_URI, PROJECT_ROOT
from energy_forecast.models.train import dvc_raw_versions

DEFAULT_MAX_MAPE = 5.0  # LK-01 acceptance threshold, in percent.


def validate_metrics(metrics, max_mape=DEFAULT_MAX_MAPE):
    """Reject missing, invalid, or excessive holdout metrics."""
    if not math.isfinite(max_mape) or max_mape <= 0:
        raise ValueError("max_mape must be positive and finite")
    for name in ("rmse", "mae", "mape"):
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid {name}: {value}")
    if metrics["mape"] > max_mape:
        raise ValueError(
            f"MAPE {metrics['mape']:.4f}% exceeds LK-01 threshold {max_mape:.2f}%"
        )


def verified_run(best, client, max_mape):
    """Compare the training manifest to its completed MLflow run and DVC files."""
    run = client.get_run(best["run_id"])
    if run.info.status != "FINISHED":
        raise ValueError(f"MLflow run is not FINISHED: {run.info.status}")
    metrics = run.data.metrics
    validate_metrics(metrics, max_mape)
    for name in ("rmse", "mae", "mape"):
        if not math.isclose(metrics[name], best[name], rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError(f"Manifest {name} does not match MLflow")
    if run.data.params.get("data_md5") != best["data_md5"]:
        raise ValueError("Training dataset hash differs from MLflow")
    for key, value in dvc_raw_versions().items():
        if run.data.params.get(key) != value:
            raise ValueError(f"DVC lineage differs from MLflow: {key}")
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "register"))
    parser.add_argument("--tracking-uri", default=MLFLOW_TRACKING_URI)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs")
    parser.add_argument("--max-mape", type=float, default=DEFAULT_MAX_MAPE)
    args = parser.parse_args()

    best = json.loads((args.output_dir / "best_run.json").read_text(encoding="utf-8"))
    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_registry_uri(args.tracking_uri)
    client = MlflowClient()
    verified_run(best, client, args.max_mape)
    report_path = args.output_dir / "automation_validation.json"

    if args.action == "validate":
        report = {
            "status": "passed",
            "run_id": best["run_id"],
            "data_md5": best["data_md5"],
            "mape": best["mape"],
            "max_mape": args.max_mape,
            "git_sha": os.getenv("GITHUB_SHA", "local"),
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Validation passed: MAPE {best['mape']:.4f}% <= {args.max_mape:.2f}%")
        return

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("status") != "passed"
        or report.get("run_id") != best["run_id"]
        or report.get("data_md5") != best["data_md5"]
        or report.get("git_sha") != os.getenv("GITHUB_SHA", "local")
        or report.get("max_mape") != args.max_mape
    ):
        raise ValueError(
            "Validation report does not match this run, data, commit, and threshold"
        )
    version = mlflow.register_model(best["model_uri"], best["model_name"])
    client.transition_model_version_stage(
        best["model_name"], version.version, "Staging"
    )
    client.set_model_version_tag(
        best["model_name"], version.version, "git_sha", report["git_sha"]
    )
    client.set_model_version_tag(
        best["model_name"], version.version, "data_md5", best["data_md5"]
    )
    print(f"Registered {best['model_name']} v{version.version} as Staging")


if __name__ == "__main__":
    main()
