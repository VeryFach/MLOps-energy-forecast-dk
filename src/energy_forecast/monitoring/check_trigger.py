import subprocess
import sys

import pandas as pd

from energy_forecast.config import LOGS_DIR

MAPE_HISTORY_PATH = LOGS_DIR / "mape_history.csv"

MAPE_THRESHOLD = 5.0
CONSECUTIVE_DAYS = 3


def load_mape_history():
    if not MAPE_HISTORY_PATH.exists():
        print(f"Riwayat MAPE tidak ditemukan: {MAPE_HISTORY_PATH}")
        return pd.DataFrame(columns=["date", "mape"])
    return pd.read_csv(MAPE_HISTORY_PATH)


def check_trigger():
    history = load_mape_history()
    if len(history) < CONSECUTIVE_DAYS:
        print(f"Riwayat MAPE belum cukup: {len(history)}/{CONSECUTIVE_DAYS} hari.")
        return False

    recent = history.tail(CONSECUTIVE_DAYS)
    dates = " -> ".join(recent["date"].astype(str))
    values = ", ".join(f"{m:.2f}%" for m in recent["mape"])
    print(f"MAPE 3 hari terakhir ({dates}): {values}")

    if (recent["mape"] > MAPE_THRESHOLD).all():
        print(f"MAPE > {MAPE_THRESHOLD}% selama {CONSECUTIVE_DAYS} hari berturut-turut. Menjalankan retraining...")
        return True
    print(f"MAPE dalam batas normal (≤ {MAPE_THRESHOLD}%). Tidak perlu retraining.")
    return False


def main():
    if check_trigger():
        result = subprocess.run([sys.executable, "-m", "energy_forecast.models.train_baseline"])
        if result.returncode != 0:
            print(f"Retraining gagal (exit code {result.returncode}).")
            sys.exit(result.returncode)
        print("Retraining selesai. Model baseline diperbarui.")
    else:
        print("Trigger tidak aktif.")


if __name__ == "__main__":
    main()