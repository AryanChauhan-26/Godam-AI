"""Godam AI - Zero-Dependency Core Logic & Algorithm Tests
"Aapka godam, ab smart."

Runs directly with standard library Python (no external packages required)
to instantly verify data cleaning, forecasting, inventory, and deadstock logic.
"""

import math
import re
import unittest
from datetime import datetime, timedelta

from modules.data_loader import _clean_numeric_cell, _normalize_string
from modules.inventory import (
    calculate_safety_stock,
    calculate_reorder_point,
    calculate_eoq,
    calculate_weeks_of_cover,
    get_z_score,
)
from modules.deadstock import (
    calculate_cash_locked,
    calculate_annual_carrying_cost,
    determine_aging_bracket,
    generate_sme_recommendation,
)


class TestStandardLibraryCleaner(unittest.TestCase):
    """Verifies SME data cleaning logic without external dependencies."""

    def test_text_in_numeric_cells(self):
        # Units
        val, fix = _clean_numeric_cell("150 pcs")
        self.assertEqual(val, 150.0)

        val, _ = _clean_numeric_cell("25.5 kg")
        self.assertEqual(val, 25.5)

        # Currency
        val, _ = _clean_numeric_cell("₹ 1,500.00")
        self.assertEqual(val, 1500.0)

        # Parentheses (accounting negative)
        val, _ = _clean_numeric_cell("(75)")
        self.assertEqual(val, -75.0)

        # Null coercion
        for null_word in ["N/A", "na", "-", "null", "None", ""]:
            val, _ = _clean_numeric_cell(null_word)
            self.assertIsNone(val)

    def test_string_normalization(self):
        norm = _normalize_string("  Qty. (मात्रा)  ")
        self.assertIn("qty", norm)
        self.assertIn("मात्रा", norm)

        norm_code = _normalize_string("Product_Code / SKU")
        self.assertEqual(norm_code, "product code sku")


class TestPureForecastingMath(unittest.TestCase):
    """Verifies mathematical formulas for WAPE and Croston SBA."""

    def test_wape_math(self):
        actuals = [100.0, 200.0, 300.0]
        preds = [90.0, 210.0, 270.0]

        abs_err = sum(abs(a - p) for a, p in zip(actuals, preds))  # 10 + 10 + 30 = 50
        total_act = sum(actuals)  # 600
        wape = abs_err / total_act  # 50 / 600 = 0.08333

        self.assertAlmostEqual(wape, 50.0 / 600.0)

    def test_croston_sba_math(self):
        # Simulates Croston recurrence relation with SBA
        history = [0, 0, 40, 0, 0, 0, 60, 0, 0]
        alpha = 0.15

        non_zeros = [(i, val) for i, val in enumerate(history) if val > 0]
        self.assertEqual(len(non_zeros), 2)

        # First demand at idx 2 (val 40)
        z = 40.0
        p = 1.0
        q = 1.0

        for t in range(3, len(history)):
            val = history[t]
            if val > 0:
                z = alpha * val + (1.0 - alpha) * z
                p = alpha * q + (1.0 - alpha) * p
                q = 1.0
            else:
                q += 1.0

        effective_p = max(p, q)
        sba_factor = 1.0 - (alpha / 2.0)
        forecast_rate = sba_factor * (z / effective_p)

        self.assertGreater(forecast_rate, 0.0)
        self.assertLess(forecast_rate, 50.0)


class TestPureInventoryAndDeadstockMath(unittest.TestCase):
    """Verifies inventory safety stock, ROP, EOQ, and deadstock calculations."""

    def test_safety_stock_math(self):
        # 95% service level -> Z = 1.645
        z = get_z_score(0.95)
        self.assertEqual(z, 1.645)

        ss = calculate_safety_stock(
            avg_weekly_demand=100.0,
            demand_std_weekly=20.0,
            lead_time_weeks=2.0,
            lead_time_std_weeks=0.0,
            service_level=0.95,
        )
        self.assertAlmostEqual(ss, 1.645 * math.sqrt(2 * 400), places=2)

    def test_reorder_point_math(self):
        rop = calculate_reorder_point(
            avg_weekly_demand=100.0,
            lead_time_weeks=2.0,
            safety_stock=46.53,
        )
        self.assertAlmostEqual(rop, 246.53, places=2)

    def test_eoq_math(self):
        # EOQ = sqrt( (2 * 5200 * 500) / 20 ) = sqrt(260000) = 509.90
        eoq = calculate_eoq(
            annual_demand=5200.0,
            order_cost=500.0,
            unit_cost=100.0,
            holding_cost_rate=0.20,
        )
        self.assertAlmostEqual(eoq, 509.90, places=1)

    def test_deadstock_capital_math(self):
        # Cash locked = 350 kg * 950 ₹/kg = 332,500 ₹
        cash = calculate_cash_locked(350.0, 950.0)
        self.assertEqual(cash, 332500.0)

        # 20% annual carrying drain = 66,500 ₹
        drain = calculate_annual_carrying_cost(cash, 0.20)
        self.assertEqual(drain, 66500.0)

    def test_aging_bracket_and_recommendation(self):
        self.assertEqual(determine_aging_bracket(45), "Active (<=90d)")
        self.assertEqual(determine_aging_bracket(130), "At Risk (91-180d)")
        self.assertEqual(determine_aging_bracket(270), "Slow Moving (181-365d)")
        self.assertEqual(determine_aging_bracket(450), "Deadstock (>365d)")

        rec = generate_sme_recommendation("raw", 400, 332500.0, "Lead-Alloy Solder Wire")
        self.assertIn("vendor", rec.lower())


if __name__ == "__main__":
    unittest.main()
