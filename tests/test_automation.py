"""Acceptance gate tests; collected by pytest or Python unittest."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from energy_forecast.models import automation


class ValidationGateTests(unittest.TestCase):
    def test_mape_at_threshold_passes(self):
        automation.validate_metrics({"rmse": 200, "mae": 150, "mape": 5.0})

    def test_bad_metrics_stop_registry(self):
        cases = [
            {"rmse": 200, "mae": 150, "mape": 5.01},
            {"rmse": 200, "mae": 150, "mape": float("nan")},
            {"rmse": 200, "mae": 150},
            {"rmse": -1, "mae": 150, "mape": 4.0},
        ]
        for metrics in cases:
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                automation.validate_metrics(metrics)

    def test_mlflow_lineage_must_match_dvc(self):
        best = {
            "run_id": "abc",
            "rmse": 200.0,
            "mae": 150.0,
            "mape": 4.0,
            "data_md5": "processed",
        }
        run = SimpleNamespace(
            info=SimpleNamespace(status="FINISHED"),
            data=SimpleNamespace(
                metrics={"rmse": 200.0, "mae": 150.0, "mape": 4.0},
                params={"data_md5": "processed", "consumption_dvc_md5": "wrong"},
            ),
        )
        client = SimpleNamespace(get_run=lambda run_id: run)
        with (
            patch.object(
                automation,
                "dvc_raw_versions",
                return_value={"consumption_dvc_md5": "expected"},
            ),
            self.assertRaisesRegex(ValueError, "DVC lineage"),
        ):
            automation.verified_run(best, client, 5.0)


if __name__ == "__main__":
    unittest.main()
