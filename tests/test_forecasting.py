"""Godam AI - Unit & Integration Tests for Forecasting Module
"Aapka godam, ab smart."

Tests cover:
1. Daily sales aggregation to weekly buckets with zero-filling
2. WAPE metric calculation and zero-demand edge cases
3. Forecasting algorithms (Moving Average, Exponential Smoothing, Croston's Method)
4. 8-week backtesting tournament and model selection
5. Cold-start short history rule (< 12 weeks -> Moving Average + "low confidence")
6. 12-week forward projections with non-negative lower/upper bounds
7. End-to-end forecasting across all catalog items in sample_data/sales.csv
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError:
    raise SystemExit(
        "\n❌ numpy or pandas is not installed. Please install project dependencies first:\n"
        "   pip install -r requirements.txt\n"
    )

from modules.data_loader import load_sales
from modules.forecasting import (
    CrostonForecast,
    ExponentialSmoothingForecast,
    MovingAverageForecast,
    ProductForecastResult,
    aggregate_sales_to_weekly,
    backtest_and_select_model,
    calculate_wape,
    forecast_all_products,
    forecast_single_product,
    get_forecast_summary_table,
)


class TestWeeklyAggregation(unittest.TestCase):
    """Tests aggregating daily sales to weekly continuous series with zero-filling."""

    def test_weekly_resampling_and_zero_filling(self):
        # Create 3 transactions across a 4-week span with week 2 missing
        records = [
            {"date": "2025-01-06", "product_id": "P1", "product_name": "Pin", "quantity": 10},
            {"date": "2025-01-08", "product_id": "P1", "product_name": "Pin", "quantity": 15},
            # Missing week around 2025-01-13
            {"date": "2025-01-20", "product_id": "P1", "product_name": "Pin", "quantity": 30},
            {"date": "2025-01-27", "product_id": "P1", "product_name": "Pin", "quantity": 25},
        ]
        df = pd.DataFrame(records)
        weekly_map = aggregate_sales_to_weekly(df)

        self.assertIn("P1", weekly_map)
        pname, weekly_df = weekly_map["P1"]
        self.assertEqual(pname, "Pin")

        # Total weeks should be 4 (including the zero-demand week)
        self.assertEqual(len(weekly_df), 4)

        # First week sum = 10 + 15 = 25
        self.assertEqual(weekly_df["quantity"].iloc[0], 25.0)

        # Second week was missing in sales data, so zero-filling must ensure 0.0
        self.assertEqual(weekly_df["quantity"].iloc[1], 0.0)

        # Third week = 30.0, Fourth week = 25.0
        self.assertEqual(weekly_df["quantity"].iloc[2], 30.0)
        self.assertEqual(weekly_df["quantity"].iloc[3], 25.0)


class TestMetricsAndAlgorithms(unittest.TestCase):
    """Tests WAPE accuracy calculation and individual forecasting methods."""

    def test_wape_calculation(self):
        actual = np.array([100.0, 200.0, 300.0])
        # Perfect prediction
        self.assertEqual(calculate_wape(actual, actual), 0.0)

        # 10% under-prediction on all periods: abs_err = 10 + 20 + 30 = 60; sum = 600 -> WAPE = 0.10
        pred_under = np.array([90.0, 180.0, 270.0])
        self.assertAlmostEqual(calculate_wape(actual, pred_under), 0.10)

        # Zero actual demand handling
        zeros = np.zeros(3)
        self.assertEqual(calculate_wape(zeros, zeros), 0.0)
        self.assertEqual(calculate_wape(zeros, np.array([10.0, 0.0, 0.0])), 1.0)

    def test_croston_intermittent_demand(self):
        """Tests Croston's method with sporadic/lumpy demand."""
        # 12 weeks with only 3 non-zero demand events
        intermittent_history = np.array([0, 0, 50, 0, 0, 0, 60, 0, 0, 0, 40, 0], dtype=float)
        forecast, std_err = CrostonForecast.fit_predict(intermittent_history, horizon=8, alpha=0.15)

        self.assertEqual(len(forecast), 8)
        # Average non-zero demand is ~50 every 3-4 weeks, so weekly rate should be ~10-15
        self.assertGreater(forecast[0], 5.0)
        self.assertLess(forecast[0], 25.0)
        self.assertGreater(std_err, 0.0)

    def test_exponential_smoothing_projection(self):
        """Tests Exponential Smoothing projection and non-negativity."""
        trend_history = np.array([10, 12, 14, 17, 20, 22, 25, 29, 31, 35, 38, 42], dtype=float)
        forecast, std_err = ExponentialSmoothingForecast.fit_predict(trend_history, horizon=12)

        self.assertEqual(len(forecast), 12)
        # Demand should continue upward trend above the last historical value
        self.assertGreater(forecast[0], 35.0)
        self.assertTrue(np.all(forecast >= 0.0))

    def test_moving_average_projection(self):
        """Tests 4-week Moving Average."""
        history = np.array([50, 60, 70, 80, 90, 100], dtype=float)
        forecast, std_err = MovingAverageForecast.fit_predict(history, horizon=12, window=4)

        # Last 4 observations: 70, 80, 90, 100 -> mean = 85.0
        self.assertEqual(len(forecast), 12)
        self.assertAlmostEqual(forecast[0], 85.0)


class TestBacktestingAndSelection(unittest.TestCase):
    """Tests 8-week backtesting tournament and winning model selection."""

    def test_backtest_picks_lowest_wape(self):
        dates = pd.date_range("2024-01-01", periods=24, freq="W-MON")
        # Steady flat demand
        quantities = np.full(24, 100.0)

        best_model, wape_scores, best_wape = backtest_and_select_model(
            weekly_dates=pd.Series(dates),
            weekly_quantities=quantities,
            backtest_weeks=8,
        )

        self.assertIn("Moving Average", wape_scores)
        self.assertIn("Exponential Smoothing", wape_scores)
        # On flat data, Moving Average achieves near 0% WAPE
        self.assertLess(best_wape, 0.05)


class TestShortHistoryRule(unittest.TestCase):
    """Tests the cold-start rule for products with < 12 weeks of data."""

    def test_under_12_weeks_uses_moving_average_and_flags_low_confidence(self):
        dates = pd.date_range("2025-01-01", periods=6, freq="W-MON")
        weekly_df = pd.DataFrame({
            "week_date": dates,
            "quantity": [40.0, 45.0, 50.0, 55.0, 60.0, 65.0],
        })

        res = forecast_single_product(
            product_id="PRD-NEW",
            product_name="New Prototype Switch",
            weekly_df=weekly_df,
            forecast_horizon=12,
        )

        # Must flag low confidence
        self.assertEqual(res.confidence, "low confidence")
        self.assertIn("Simple Moving Average", res.best_model)
        self.assertEqual(len(res.forecast_df), 12)
        # All bounds must be >= 0
        self.assertTrue((res.forecast_df["lower_bound"] >= 0).all())
        self.assertTrue((res.forecast_df["upper_bound"] >= res.forecast_df["forecast"]).all())


class TestEndToEndSampleDataForecasting(unittest.TestCase):
    """Integration test: runs full forecasting pipeline on sample_data/sales.csv."""

    def test_forecast_all_products_from_sample_data(self):
        sample_sales_path = Path(__file__).resolve().parent.parent / "sample_data" / "sales.csv"
        self.assertTrue(sample_sales_path.exists(), "sales.csv must exist in sample_data")

        # Load and clean sales
        sales_df, report = load_sales(sample_sales_path)
        self.assertGreater(len(sales_df), 1000)

        # Run multi-model forecast tournament across all products
        results = forecast_all_products(sales_df, forecast_horizon=12, backtest_weeks=8)

        # Check that all finished goods from sample data were forecasted
        self.assertGreaterEqual(len(results), 8)

        for pid, res in results.items():
            # Validate output contract
            self.assertIsInstance(res, ProductForecastResult)
            self.assertEqual(len(res.forecast_df), 12)
            self.assertIn(res.confidence, ["high", "medium", "low confidence"])
            self.assertGreaterEqual(res.accuracy_pct, 0.0)
            self.assertLessEqual(res.accuracy_pct, 100.0)

            # Ensure bounds validity: lower_bound <= forecast <= upper_bound and lower >= 0
            fdf = res.forecast_df
            self.assertTrue((fdf["lower_bound"] >= 0).all())
            self.assertTrue((fdf["forecast"] >= fdf["lower_bound"]).all())
            self.assertTrue((fdf["upper_bound"] >= fdf["forecast"]).all())

        # Test deadstock / slow mover item FG-108
        if "FG-108" in results:
            fg108 = results["FG-108"]
            # FG-108 stopped selling 9 months ago in sample data, so forecast should be very low
            avg_forecast = fg108.forecast_df["forecast"].mean()
            self.assertLess(avg_forecast, 15.0)

        # Test summary table generation
        summary_table = get_forecast_summary_table(results)
        self.assertEqual(len(summary_table), len(results))
        self.assertIn("Total 12W Forecast", summary_table.columns)
        self.assertIn("Accuracy %", summary_table.columns)


class TestForecastingEdgeCases(unittest.TestCase):
    """Tests defensive guards for empty inputs, custom column names, and missing dates."""

    def test_custom_quantity_column_name(self):
        df = pd.DataFrame([
            {"date": "2025-01-06", "product_id": "P1", "sold_qty": 10},
            {"date": "2025-01-13", "product_id": "P1", "sold_qty": 20},
        ])
        res = aggregate_sales_to_weekly(df, quantity_col="sold_qty")
        self.assertIn("P1", res)
        pname, weekly_df = res["P1"]
        self.assertIn("quantity", weekly_df.columns)
        self.assertEqual(weekly_df["quantity"].iloc[0], 10.0)

    def test_empty_dataframe_and_none(self):
        self.assertEqual(aggregate_sales_to_weekly(None), {})
        self.assertEqual(aggregate_sales_to_weekly(pd.DataFrame()), {})
        self.assertEqual(forecast_all_products(pd.DataFrame()), {})

    def test_empty_product_forecast(self):
        res = forecast_single_product("EMPTY-1", "Empty SKU", pd.DataFrame())
        self.assertEqual(res.history_weeks, 0)
        self.assertEqual(len(res.forecast_df), 12)
        self.assertEqual(res.forecast_df["forecast"].sum(), 0.0)
        self.assertEqual(res.confidence, "low confidence")


if __name__ == "__main__":
    unittest.main()

