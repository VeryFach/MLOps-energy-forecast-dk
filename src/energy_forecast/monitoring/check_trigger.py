import subprocess
import sys

import pandas as pd

from energy_forecast.config import DRIFT_LOG_PATH, LOGS_DIR, MAPE_HISTORY_PATH

MAPE_THRESHOLD = 5.0
CONSECUTIVE_DAYS = 3


def load_mape_history() -> pd.DataFrame:
    if not MAPE_HISTORY_PATH.exists():
        print(f"MAPE history not found: {MAPE_HISTORY_PATH}")
        return pd.DataFrame(columns=["date", "mape"])
    return pd.read_csv(MAPE_HISTORY_PATH)


def load_drift_log() -> pd.DataFrame:
    if not DRIFT_LOG_PATH.exists():
        print(f"Drift log not found: {DRIFT_LOG_PATH}")
        return pd.DataFrame(columns=["date", "signal", "value", "drifted"])
    return pd.read_csv(DRIFT_LOG_PATH)


def check_mape_trigger(history: pd.DataFrame) -> bool:
    if len(history) < CONSECUTIVE_DAYS:
        print(f"MAPE history insufficient: {len(history)}/{CONSECUTIVE_DAYS} days.")
        return False

    recent = history.tail(CONSECUTIVE_DAYS)
    dates = " -> ".join(recent["date"].astype(str))
    values = ", ".join(f"{m:.2f}%" for m in recent["mape"])
    print(f"MAPE last 3 days ({dates}): {values}")

    if (recent["mape"] > MAPE_THRESHOLD).all():
        print(f"MAPE > {MAPE_THRESHOLD}% for {CONSECUTIVE_DAYS} consecutive days. Triggering retraining...")
        return True

    print(f"MAPE within normal range (<= {MAPE_THRESHOLD}%).")
    return False


def check_drift_trigger(drift_log: pd.DataFrame) -> bool:
    if drift_log.empty:
        print("No drift data available.")
        return False

    today = pd.Timestamp.now().date().isoformat()
    today_drifts = drift_log[drift_log["date"] == today]

    if today_drifts.empty:
        print(f"No drift data for today ({today}).")
        return False

    drifted_signals = today_drifts[today_drifts["drifted"] == True]
    if not drifted_signals.empty:
        signal_names = drifted_signals["signal"].tolist()
        print(f"Drift detected in signals: {signal_names}. Triggering retraining...")
        return True

    print("No drift signals exceeded thresholds.")
    return False


def run_retraining(model_type: str = "baseline") -> bool:
    module = f"energy_forecast.models.train_{model_type}"
    print(f"Running retraining: {module}")
    result = subprocess.run([sys.executable, "-m", module])
    if result.returncode != 0:
        print(f"Retraining failed (exit code {result.returncode}).")
        return False
    print("Retraining completed successfully.")
    return True


def main():
    mape_history = load_mape_history()
    drift_log = load_drift_log()

    mape_triggered = check_mape_trigger(mape_history)
    drift_triggered = check_drift_trigger(drift_log)

    if mape_triggered or drift_triggered:
        reason = []
        if mape_triggered:
            reason.append("MAPE threshold exceeded")
        if drift_triggered:
            reason.append("drift signals detected")
        print(f"Retraining triggered by: {', '.join(reason)}")
        run_retraining("baseline")
    else:
        print("No trigger active. Model is stable.")


if __name__ == "__main__":
    main()
