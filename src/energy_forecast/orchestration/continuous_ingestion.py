import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from energy_forecast.config import REFRESH_INTERVAL_MINUTES

MODULES = (
    "energy_forecast.data.fetch_energy_dk",
    "energy_forecast.data.fetch_weather",
    "energy_forecast.data.merge_data",
)

_stop_requested = False
HEARTBEAT_PATH = os.getenv("INGESTION_HEARTBEAT_PATH", "/app/logs/ingestion.heartbeat")


def _request_stop(signum: int, _frame: object) -> None:
    global _stop_requested
    _stop_requested = True
    print(f"Received signal {signum}; stopping after the current step.", flush=True)


def run_module(module: str) -> None:
    retry_delay_seconds = float(os.getenv("INGESTION_RETRY_DELAY_SECONDS", "60"))
    max_attempts = int(os.getenv("INGESTION_MAX_ATTEMPTS", "3"))
    if retry_delay_seconds < 0:
        raise ValueError("INGESTION_RETRY_DELAY_SECONDS must not be negative")
    if max_attempts < 1:
        raise ValueError("INGESTION_MAX_ATTEMPTS must be at least one")

    for attempt in range(1, max_attempts + 1):
        print(f"=== Running {module} (attempt {attempt}/{max_attempts}) ===", flush=True)
        try:
            subprocess.run([sys.executable, "-m", module], check=True)
            return
        except subprocess.CalledProcessError:
            if attempt == max_attempts:
                raise
            delay = retry_delay_seconds * (2 ** (attempt - 1))
            print(
                f"{module} failed; retrying in {delay:g} seconds.",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)


def run_once() -> None:
    Path(HEARTBEAT_PATH).touch()
    for module in MODULES:
        run_module(module)
    print("Ingestion cycle completed.", flush=True)


def main() -> None:
    interval_minutes = float(
        os.getenv("INGESTION_INTERVAL_MINUTES", str(REFRESH_INTERVAL_MINUTES))
    )
    if interval_minutes <= 0:
        raise ValueError("INGESTION_INTERVAL_MINUTES must be greater than zero")

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    interval_seconds = interval_minutes * 60

    while not _stop_requested:
        try:
            run_once()
        except subprocess.CalledProcessError as error:
            print(
                f"Ingestion cycle failed in {error.cmd} with exit code "
                f"{error.returncode}; retrying after the interval.",
                file=sys.stderr,
                flush=True,
            )

        if not _stop_requested:
            print(
                f"Waiting {interval_minutes:g} minutes before the next cycle.",
                flush=True,
            )
            deadline = time.monotonic() + interval_seconds
            while not _stop_requested and time.monotonic() < deadline:
                Path(HEARTBEAT_PATH).touch()
                time.sleep(min(30, deadline - time.monotonic()))

    print("Continuous ingestion stopped.", flush=True)


if __name__ == "__main__":
    main()
