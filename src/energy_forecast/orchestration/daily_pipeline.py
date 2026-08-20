import subprocess
import sys

from energy_forecast.config import PROJECT_ROOT

SCRIPTS = [
    "energy_forecast.data.fetch_energy_dk",
    "energy_forecast.data.fetch_weather",
    "energy_forecast.data.merge_data",
]

TASK_NAME = "EnergyForecastDK_Daily"
SCHEDULE_TIME = "01:00"


def setup_task():
    python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    command = f'"{python}" -m energy_forecast.orchestration.daily_pipeline'

    result = subprocess.run(
        [
            "schtasks",
            "/create",
            "/tn", TASK_NAME,
            "/tr", command,
            "/sc", "daily",
            "/st", SCHEDULE_TIME,
            "/f",
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip())
        sys.exit(result.returncode)
    print(f"Task Scheduler '{TASK_NAME}' berhasil diatur setiap hari pukul {SCHEDULE_TIME}.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--setup-task":
        setup_task()
        return

    for module in SCRIPTS:
        print(f"=== Menjalankan {module} ===")
        result = subprocess.run([sys.executable, "-m", module])
        if result.returncode != 0:
            print(f"Gagal: {module} (exit code {result.returncode})")
            sys.exit(result.returncode)

    print("Pipeline harian selesai.")


if __name__ == "__main__":
    main()