import subprocess
import sys

from energy_forecast.config import PROJECT_ROOT

SCRIPTS = [
    "energy_forecast.data.fetch_energy_dk",
    "energy_forecast.data.fetch_weather",
    "energy_forecast.data.merge_data",
]


def main():
    for module in SCRIPTS:
        print(f"=== Running {module} ===")
        result = subprocess.run([sys.executable, "-m", module])
        if result.returncode != 0:
            print(f"Failed: {module} (exit code {result.returncode})")
            sys.exit(result.returncode)

    print("Daily pipeline completed.")
    print("Note: For scheduled execution, use the Airflow DAG at dags/energy_forecast_dag.py")


if __name__ == "__main__":
    main()
