import subprocess
import sys

from prefect import flow, task
from prefect.client.schemas.schedules import CronSchedule

from energy_forecast.config import LOGS_DIR

MODULES = {
    "fetch_energy": "energy_forecast.data.fetch_energy_dk",
    "fetch_weather": "energy_forecast.data.fetch_weather",
    "merge": "energy_forecast.data.merge_data",
    "evaluate": "energy_forecast.monitoring.evaluate_model",
    "train_baseline": "energy_forecast.models.train_baseline",
}


@task
def run_module(name: str) -> str:
    print(f"=== Menjalankan {name} ===")
    result = subprocess.run(
        [sys.executable, "-m", name],
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"{name} gagal (exit {result.returncode}): {result.stderr}")
    return result.stdout


@task
def evaluate() -> float:
    run_module(MODULES["evaluate"])
    history = LOGS_DIR / "mape_history.csv"
    if not history.exists():
        raise FileNotFoundError("mape_history.csv tidak ditemukan")
    with open(history, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()][1:]
    if len(lines) < 3:
        print(f"Riwayat MAPE belum cukup: {len(lines)}/3 hari.")
        return 0.0
    mape_values = [float(l.split(",")[1]) for l in lines[-3:]]
    print(f"MAPE 3 hari terakhir: {mape_values}")
    return max(mape_values)


@task
def check_trigger(last_mape: float) -> bool:
    if last_mape > 5.0:
        print("MAPE > 5%. Menjalankan retraining...")
        run_module(MODULES["train_baseline"])
        return True
    print("MAPE dalam batas normal. Tidak perlu retraining.")
    return False


@flow
def energy_forecast_daily_flow():
    run_module(MODULES["fetch_energy"])
    run_module(MODULES["fetch_weather"])
    run_module(MODULES["merge"])
    last_mape = evaluate()
    check_trigger(last_mape)
    print("Workflow harian selesai.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        energy_forecast_daily_flow.serve(
            name="energy-forecast-daily",
            schedules=[CronSchedule(cron="0 1 * * *", timezone="Europe/Copenhagen")],
            tags=["daily", "energy-forecast"],
        )
    else:
        energy_forecast_daily_flow()
