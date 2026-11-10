"""Godam AI - Unit & Integration Tests for Inventory & Deadstock Modules
"Aapka godam, ab smart."

Tests cover:
1. Inventory Formulas: Safety Stock, Reorder Point, EOQ, Weeks of Cover
2. Alert generation with stockout projections and urgency rankings (Critical, Soon, OK)
3. Deadstock Detection: 90+ days threshold, aging brackets, cash locked in ₹
4. End-to-end integration with sample_data (stock.csv, purchases.csv, sales.csv)
"""

import math
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

from modules.data_loader import load_purchases, load_sales, load_stock
from modules.deadstock import (
    DeadstockAnalyzer,
    DeadstockReport,
    calculate_annual_carrying_cost,
    calculate_cash_locked,
    determine_aging_bracket,
)
from modules.forecasting import forecast_all_products
from modules.inventory import (
    InventoryOptimizer,
    calculate_eoq,
    calculate_reorder_point,
    calculate_safety_stock,
    calculate_weeks_of_cover,
    get_z_score,
)


class TestInventoryFormulas(unittest.TestCase):
    """Tests core mathematical formulas for inventory control."""

    def test_z_score_lookup(self):
        self.assertAlmostEqual(get_z_score(0.95), 1.645)
        self.assertAlmostEqual(get_z_score(0.90), 1.282)
        self.assertAlmostEqual(get_z_score(0.99), 2.326)

    def test_safety_stock_calculation(self):
        # Weekly demand = 100, demand_std = 20, lead_time = 2 weeks (constant lead time)
        # SS = 1.645 * sqrt(2 * 20^2 + 0) = 1.645 * sqrt(800) = 1.645 * 28.284 = 46.52
        ss = calculate_safety_stock(
            avg_weekly_demand=100.0,
            demand_std_weekly=20.0,
            lead_time_weeks=2.0,
            lead_time_std_weeks=0.0,
            service_level=0.95,
        )
        self.assertAlmostEqual(ss, 1.645 * math.sqrt(800.0), places=1)

    def test_safety_stock_with_lead_time_variability(self):
        # When supplier is erratic (lead_time_std > 0), safety stock must increase
        ss_fixed = calculate_safety_stock(100.0, 20.0, 2.0, 0.0, 0.95)
        ss_variable = calculate_safety_stock(100.0, 20.0, 2.0, 0.5, 0.95)
        self.assertGreater(ss_variable, ss_fixed)

    def test_reorder_point_calculation(self):
        # ROP = (Demand * Lead_time) + SS
        # 100 * 2 weeks + 46.5 = 246.5
        rop = calculate_reorder_point(
            avg_weekly_demand=100.0,
            lead_time_weeks=2.0,
            safety_stock=46.5,
        )
        self.assertAlmostEqual(rop, 246.5)

    def test_eoq_calculation(self):
        # Annual Demand = 5,200 units (100/wk * 52)
        # Order Cost S = ₹ 500, Unit Cost = ₹ 100, Holding rate = 20% (H = ₹ 20/unit/yr)
        # EOQ = sqrt( (2 * 5200 * 500) / 20 ) = sqrt(260,000) = 509.9 units
        eoq = calculate_eoq(
            annual_demand=5200.0,
            order_cost=500.0,
            unit_cost=100.0,
            holding_cost_rate=0.20,
        )
        expected_eoq = math.sqrt((2 * 5200 * 500) / 20)
        self.assertAlmostEqual(eoq, expected_eoq, places=1)

    def test_weeks_of_cover(self):
        qty = calculate_weeks_of_cover(avg_weekly_demand=50.0, target_weeks=4.0)
        self.assertEqual(qty, 200.0)


class TestDeadstockFormulas(unittest.TestCase):
    """Tests deadstock and working capital calculations."""

    def test_cash_locked_and_carrying_cost(self):
        qty = 350.0
        cost = 950.0
        locked = calculate_cash_locked(qty, cost)
        self.assertEqual(locked, 332500.0)

        # 20% carrying drain per year
        drain = calculate_annual_carrying_cost(locked, 0.20)
        self.assertEqual(drain, 66500.0)

    def test_aging_bracket_classification(self):
        self.assertEqual(determine_aging_bracket(45), "Active (<=90d)")
        self.assertEqual(determine_aging_bracket(120), "At Risk (91-180d)")
        self.assertEqual(determine_aging_bracket(250), "Slow Moving (181-365d)")
        self.assertEqual(determine_aging_bracket(400), "Deadstock (>365d)")


class TestUrgencyAndAlerts(unittest.TestCase):
    """Tests alert generation and urgency classification."""

    def setUp(self):
        self.optimizer = InventoryOptimizer(service_level=0.95)

    def test_critical_alert_when_stock_below_rop(self):
        # Current stock = 50, but ROP = 100 -> Critical!
        ref_date = datetime(2026, 11, 1)
        metrics = self.optimizer.optimize_material(
            material_id="RM-TEST",
            material_name="Test Chemical",
            unit="kg",
            current_stock=30.0,
            unit_cost=200.0,
            avg_weekly_demand=70.0,  # 10 kg/day
            demand_std_weekly=15.0,
            lead_time_days=7.0,  # 1 week lead time
            current_date=ref_date,
        )

        self.assertEqual(metrics.urgency, "Critical")
        alerts = self.optimizer.generate_alerts([metrics])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].urgency, "Critical")
        self.assertIn("Test Chemical", alerts[0].alert_message)
        self.assertIn("Order", alerts[0].alert_message)

    def test_ok_alert_when_abundant_stock(self):
        # Current stock = 1000 kg (100 days supply) -> OK
        ref_date = datetime(2026, 11, 1)
        metrics = self.optimizer.optimize_material(
            material_id="RM-OK",
            material_name="Steel Coil",
            unit="kg",
            current_stock=1000.0,
            unit_cost=80.0,
            avg_weekly_demand=70.0,  # 10 kg/day
            demand_std_weekly=10.0,
            lead_time_days=7.0,
            current_date=ref_date,
        )

        self.assertEqual(metrics.urgency, "OK")


class TestEndToEndInventoryIntegration(unittest.TestCase):
    """Integration test with generated sample data files."""

    def test_inventory_and_deadstock_analysis_with_sample_data(self):
        sample_dir = Path(__file__).resolve().parent.parent / "sample_data"
        sales_path = sample_dir / "sales.csv"
        purchases_path = sample_dir / "purchases.csv"
        stock_path = sample_dir / "stock.csv"

        self.assertTrue(sales_path.exists())
        self.assertTrue(purchases_path.exists())
        self.assertTrue(stock_path.exists())

        # Load clean datasets
        sales_df, _ = load_sales(sales_path)
        purch_df, _ = load_purchases(purchases_path)
        stock_df, _ = load_stock(stock_path)

        # 1. Run demand forecasts
        forecasts = forecast_all_products(sales_df, forecast_horizon=12, backtest_weeks=8)

        # 2. Run inventory optimizer
        optimizer = InventoryOptimizer(service_level=0.95)
        summary_df, alerts = optimizer.optimize_all(
            stock_df=stock_df,
            purchases_df=purch_df,
            product_forecasts=forecasts,
        )

        self.assertGreater(len(summary_df), 0)
        self.assertGreater(len(alerts), 0)
        self.assertIn("reorder_point", summary_df.columns)
        self.assertIn("safety_stock", summary_df.columns)
        self.assertIn("recommended_order_qty", summary_df.columns)

        # Verify alerts contain urgency ranking
        urgencies = {a.urgency for a in alerts}
        self.assertTrue(any(u in urgencies for u in ["Critical", "Soon", "OK"]))

        # 3. Run deadstock analyzer
        deadstock_analyzer = DeadstockAnalyzer(inactivity_threshold_days=90)
        report = deadstock_analyzer.analyze_inventory(
            stock_df=stock_df,
            sales_df=sales_df,
            purchases_df=purch_df,
        )

        self.assertIsInstance(report, DeadstockReport)
        self.assertGreater(report.total_cash_locked_rupees, 0.0)
        self.assertGreater(report.deadstock_items_count, 0)

        # Deadstock items must be ranked descending by cash locked
        if len(report.ranked_deadstock_items) > 1:
            first_val = report.ranked_deadstock_items[0].cash_locked_rupees
            second_val = report.ranked_deadstock_items[1].cash_locked_rupees
            self.assertGreaterEqual(first_val, second_val)

        # Ensure RM-207 (Lead-Alloy Solder Wire) and FG-108 (Legacy Fuse) are detected
        flagged_ids = [item.item_id for item in report.ranked_deadstock_items]
        self.assertTrue("RM-207" in flagged_ids or "FG-108" in flagged_ids)

        # Verify executive summary string
        summary_text = report.summary()
        self.assertIn("Godam AI Working Capital & Deadstock Diagnostic", summary_text)
        self.assertIn("₹", summary_text)


if __name__ == "__main__":
    unittest.main()

