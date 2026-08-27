import numpy as np
import pandas as pd

from energy_forecast.config import (
    DRIFT_CONSUMPTION_ZSCORE_THRESHOLD,
    DRIFT_LOG_PATH,
    DRIFT_NIGHT_DAY_RATIO_LOWER,
    DRIFT_NIGHT_DAY_RATIO_UPPER,
    DRIFT_PEAK_HOUR_SHIFT_THRESHOLD,
    DRIFT_PSI_THRESHOLD,
    LOGS_DIR,
    PROCESSED_DIR,
)


def load_data() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / "merged_data.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def calculate_psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    eps = 1e-6
    breakpoints = np.linspace(
        min(reference.min(), current.min()) - eps,
        max(reference.max(), current.max()) + eps,
        bins + 1,
    )
    ref_counts = np.histogram(reference, bins=breakpoints)[0] / len(reference)
    cur_counts = np.histogram(current, bins=breakpoints)[0] / len(current)

    ref_counts = np.clip(ref_counts, eps, None)
    cur_counts = np.clip(cur_counts, eps, None)

    psi = np.sum((cur_counts - ref_counts) * np.log(cur_counts / ref_counts))
    return float(psi)


def signal_peak_hour_psi(df: pd.DataFrame) -> dict:
    ref = df[df["datetime"] < df["datetime"].max() - pd.Timedelta(days=7)]
    cur = df[df["datetime"] >= df["datetime"].max() - pd.Timedelta(days=7)]

    ref_peak = ref[ref["hour"].isin([17, 18, 19])]["consumption_mw"].values
    cur_peak = cur[cur["hour"].isin([17, 18, 19])]["consumption_mw"].values

    if len(ref_peak) == 0 or len(cur_peak) == 0:
        return {"signal": "peak_hour_psi", "value": 0.0, "drifted": False}

    psi = calculate_psi(ref_peak, cur_peak)
    return {"signal": "peak_hour_psi", "value": round(psi, 4), "drifted": psi > DRIFT_PSI_THRESHOLD}


def signal_night_day_ratio(df: pd.DataFrame) -> dict:
    night = df[(df["hour"] >= 0) & (df["hour"] < 6)]["consumption_mw"]
    day = df[(df["hour"] >= 10) & (df["hour"] < 16)]["consumption_mw"]

    if len(night) == 0 or len(day) == 0:
        return {"signal": "night_day_ratio", "value": 0.0, "drifted": False}

    ratio = night.mean() / day.mean()
    drifted = ratio > DRIFT_NIGHT_DAY_RATIO_UPPER or ratio < DRIFT_NIGHT_DAY_RATIO_LOWER
    return {"signal": "night_day_ratio", "value": round(ratio, 4), "drifted": drifted}


def signal_mean_consumption_shift(df: pd.DataFrame) -> dict:
    recent = df.tail(168)["consumption_mw"]
    historical = df.iloc[:-168]["consumption_mw"]

    if len(recent) == 0 or len(historical) == 0:
        return {"signal": "mean_consumption_shift", "value": 0.0, "drifted": False}

    shift = recent.mean() - historical.mean()
    return {"signal": "mean_consumption_shift", "value": round(shift, 4), "drifted": abs(shift) > historical.std() * 0.5}


def signal_peak_hour_shift(df: pd.DataFrame) -> dict:
    recent = df.tail(168)
    historical = df.iloc[:-168]

    if len(recent) == 0 or len(historical) == 0:
        return {"signal": "peak_hour_shift", "value": 0, "drifted": False}

    recent_peak_hour = recent.groupby("hour")["consumption_mw"].mean().idxmax()
    hist_peak_hour = historical.groupby("hour")["consumption_mw"].mean().idxmax()

    shift = abs(recent_peak_hour - hist_peak_hour)
    return {"signal": "peak_hour_shift", "value": shift, "drifted": shift >= DRIFT_PEAK_HOUR_SHIFT_THRESHOLD}


def signal_consumption_zscore(df: pd.DataFrame) -> dict:
    recent_mean = df.tail(24)["consumption_mw"].mean()
    historical_mean = df["consumption_mw"].mean()
    historical_std = df["consumption_mw"].std()

    if historical_std == 0:
        return {"signal": "consumption_zscore", "value": 0.0, "drifted": False}

    zscore = abs(recent_mean - historical_mean) / historical_std
    return {"signal": "consumption_zscore", "value": round(zscore, 4), "drifted": zscore > DRIFT_CONSUMPTION_ZSCORE_THRESHOLD}


def run_drift_detection() -> list[dict]:
    df = load_data()
    signals = [
        signal_peak_hour_psi(df),
        signal_night_day_ratio(df),
        signal_mean_consumption_shift(df),
        signal_peak_hour_shift(df),
        signal_consumption_zscore(df),
    ]
    return signals


def save_drift_log(signals: list[dict]) -> pd.DataFrame:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().date().isoformat()

    rows = []
    for s in signals:
        rows.append({
            "date": today,
            "signal": s["signal"],
            "value": s["value"],
            "drifted": s["drifted"],
        })

    new_df = pd.DataFrame(rows)

    if DRIFT_LOG_PATH.exists():
        history = pd.read_csv(DRIFT_LOG_PATH)
        history = history[history["date"] != today]
        history = pd.concat([history, new_df], ignore_index=True)
    else:
        history = new_df

    history.to_csv(DRIFT_LOG_PATH, index=False)
    return history


def main():
    signals = run_drift_detection()
    save_drift_log(signals)

    any_drifted = any(s["drifted"] for s in signals)
    print("Drift Detection Results:")
    for s in signals:
        status = "DRIFT" if s["drifted"] else "OK"
        print(f"  [{status}] {s['signal']}: {s['value']}")

    if any_drifted:
        print("Drift detected! Consider retraining the model.")
    else:
        print("No drift detected. Model is stable.")


if __name__ == "__main__":
    main()
