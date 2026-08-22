import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def _run_module(module_name: str):
    result = subprocess.run(
        [sys.executable, "-m", module_name],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"{module_name} failed (exit {result.returncode}): {result.stderr}")


def fetch_energy():
    _run_module("energy_forecast.data.fetch_energy_dk")


def fetch_weather():
    _run_module("energy_forecast.data.fetch_weather")


def merge_data():
    _run_module("energy_forecast.data.merge_data")


def detect_drift():
    _run_module("energy_forecast.monitoring.detect_drift")


def evaluate_model():
    _run_module("energy_forecast.monitoring.evaluate_model")


def check_and_retrain():
    _run_module("energy_forecast.monitoring.check_trigger")


default_args = {
    "owner": "energy-forecast",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="energy_forecast_daily",
    default_args=default_args,
    description="Daily energy forecast pipeline for Denmark",
    schedule_interval="0 1 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["daily", "energy-forecast", "denmark"],
) as dag:

    task_fetch_energy = PythonOperator(
        task_id="fetch_energy",
        python_callable=fetch_energy,
        doc="Fetch consumption data from Energi Data Service API",
    )

    task_fetch_weather = PythonOperator(
        task_id="fetch_weather",
        python_callable=fetch_weather,
        doc="Fetch weather data from Open-Meteo API",
    )

    task_merge = PythonOperator(
        task_id="merge_data",
        python_callable=merge_data,
        doc="Merge and engineer features from raw data",
    )

    task_drift = PythonOperator(
        task_id="detect_drift",
        python_callable=detect_drift,
        doc="Run drift detection signals",
    )

    task_evaluate = PythonOperator(
        task_id="evaluate_model",
        python_callable=evaluate_model,
        doc="Evaluate model performance on latest data",
    )

    task_retrain = PythonOperator(
        task_id="check_and_retrain",
        python_callable=check_and_retrain,
        doc="Check triggers and retrain if needed",
    )

    task_fetch_energy >> task_fetch_weather >> task_merge
    task_merge >> [task_drift, task_evaluate]
    [task_drift, task_evaluate] >> task_retrain
