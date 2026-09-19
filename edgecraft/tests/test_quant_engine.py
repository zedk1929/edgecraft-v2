import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from quant_engine import generate_demo_data, load_price_csv, parameter_sweep, run_backtest


class QuantEngineTests(unittest.TestCase):
    def test_demo_data_is_repeatable_and_well_formed(self):
        first = generate_demo_data(300, seed=4)
        second = generate_demo_data(300, seed=4)
        self.assertEqual(list(first.columns), ["date", "open", "high", "low", "close", "volume"])
        self.assertEqual(len(first), 300)
        np.testing.assert_allclose(first["close"], second["close"])
        self.assertTrue((first["high"] >= first[["open", "close"]].max(axis=1)).all())
        self.assertTrue((first["low"] <= first[["open", "close"]].min(axis=1)).all())

    def test_signal_is_lagged_to_prevent_lookahead(self):
        dates = pd.bdate_range("2024-01-01", periods=160)
        prices = np.linspace(100, 180, len(dates))
        data = pd.DataFrame({"date": dates, "close": prices})
        result = run_backtest(data, "Moving Average Crossover", {"fast": 5, "slow": 20})
        first_signal = result.frame.index[result.frame["signal"] > 0][0]
        self.assertEqual(result.frame.loc[first_signal, "position"], 0)
        self.assertEqual(result.frame.loc[first_signal + 1, "position"], 1)

    def test_costs_reduce_ending_equity(self):
        data = generate_demo_data(400, seed=8)
        free = run_backtest(data, "Moving Average Crossover", {"fast": 10, "slow": 40}, fee_bps=0)
        costly = run_backtest(data, "Moving Average Crossover", {"fast": 10, "slow": 40}, fee_bps=25)
        self.assertLessEqual(costly.metrics["ending_equity"], free.metrics["ending_equity"])

    def test_csv_loader_recognizes_common_column_names(self):
        source = pd.DataFrame({
            "Date": pd.bdate_range("2025-01-01", periods=80),
            "Adj Close": np.linspace(50, 60, 80),
            "Volume": np.arange(80) + 1000,
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            source.to_csv(path, index=False)
            loaded = load_price_csv(path)
        self.assertEqual(len(loaded), 80)
        self.assertIn("close", loaded.columns)
        self.assertIn("volume", loaded.columns)

    def test_parameter_sweep_returns_ranked_results(self):
        data = generate_demo_data(350, seed=12)
        sweep = parameter_sweep(data, "Moving Average Crossover", 10_000, 5, 0.7)
        self.assertEqual(len(sweep), 16)
        self.assertTrue(sweep["train_sharpe"].is_monotonic_decreasing)
        self.assertTrue({"fast", "slow", "train_sharpe", "test_sharpe"}.issubset(sweep.columns))


if __name__ == "__main__":
    unittest.main()
