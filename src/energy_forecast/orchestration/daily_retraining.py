import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from energy_forecast.config import TIMEZONE

_stop_requested = False
HEARTBEAT_PATH = os.getenv(
    "DAILY_RETRAINING_HEARTBEAT_PATH", "/app/logs/daily-retraining.heartbeat"
)


def _request_stop(signum: int, _frame: object) -> None:
    global _stop_requested
    _stop_requested = True
    print(f"Received signal {signum}; stopping after the current step.", flush=True)


def run_module(module: str) -> None:
    print(f"=== Running {module} ===", flush=True)
    subprocess.run([sys.executable, "-m", module], check=True)


def run_script(script: str) -> None:
    print(f"=== Running {script} ===", flush=True)
    subprocess.run([sys.executable, script], check=True)


def should_retrain() -> bool:
    import pandas as pd
    import mlflow

    history_path = os.environ.get(
        "MAPE_HISTORY_PATH", "/app/logs/mape_history.csv"
    )
    history = pd.read_csv(history_path)
    if history.empty or "mape" not in history:
        raise ValueError(f"MAPE history is empty or invalid: {history_path}")

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    client = mlflow.MlflowClient()
    try:
        client.get_model_version_by_alias("energy-forecast-baseline", "champion")
        has_production_model = True
    except Exception:
        production_versions = list(
            client.search_model_versions("name='energy-forecast-baseline'")
        )
        has_production_model = any(
            version.current_stage == "Production" for version in production_versions
        )
    if not has_production_model:
        print("No Production model found; bootstrapping the first model.", flush=True)
        return True

    latest_mape = float(history.iloc[-1]["mape"])
    print(f"Latest MAPE: {latest_mape:.2f}%", flush=True)
    return latest_mape > float(os.getenv("RETRAINING_MAPE_THRESHOLD", "5.0"))


def seconds_until_next_run(hour: int, minute: int) -> float:
    timezone = ZoneInfo(TIMEZONE)
    now = datetime.now(timezone)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


def run_daily_cycle() -> None:
    Path(HEARTBEAT_PATH).touch()
    run_script("src/preprocess.py")
    run_module("energy_forecast.monitoring.evaluate_model")
    if should_retrain():
        print("MAPE exceeds threshold; starting baseline retraining.", flush=True)
        run_module("energy_forecast.models.train_baseline")
    else:
        print("MAPE is within threshold; retraining skipped.", flush=True)


def main() -> None:
    run_hour = int(os.getenv("DAILY_RETRAINING_HOUR", "1"))
    run_minute = int(os.getenv("DAILY_RETRAINING_MINUTE", "0"))
    run_on_start = os.getenv("DAILY_RETRAINING_RUN_ON_START", "false").lower() == "true"
    if not 0 <= run_hour <= 23 or not 0 <= run_minute <= 59:
        raise ValueError("DAILY_RETRAINING_HOUR/MINUTE is invalid")

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    if run_on_start:
        try:
            run_daily_cycle()
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            print(f"Daily retraining cycle failed: {error}", file=sys.stderr, flush=True)

    while not _stop_requested:
        wait_seconds = seconds_until_next_run(run_hour, run_minute)
        print(f"Next daily cycle in {wait_seconds / 3600:.2f} hours.", flush=True)
        deadline = time.monotonic() + wait_seconds
        while not _stop_requested and time.monotonic() < deadline:
            Path(HEARTBEAT_PATH).touch()
            time.sleep(min(30, deadline - time.monotonic()))
        if not _stop_requested:
            try:
                run_daily_cycle()
            except (OSError, subprocess.CalledProcessError, ValueError) as error:
                print(
                    f"Daily retraining cycle failed: {error}",
                    file=sys.stderr,
                    flush=True,
                )

    print("Daily retraining stopped.", flush=True)


if __name__ == "__main__":
    main()
