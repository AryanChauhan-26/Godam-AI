"""Godam AI - Unit Tests for Data Layer & DataLoader
"Aapka godam, ab smart."

Tests cover:
1. Column fuzzy matching & Hindi / Hinglish alias recognition ("Qty", "मात्रा", "दिनांक", etc.)
2. Cleaning text inside numeric columns ("100 pcs", "₹ 4,500.50", "20 kg", "(50)")
3. Date parsing across DD/MM/YYYY, MM/DD/YYYY, ISO, and Excel numeric serial dates
4. Duplicate row removal & empty row cleanup
5. Missing identifier and invalid date handling
6. Auto-detection of dataset types (sales, purchases, stock)
7. DataQualityReport accuracy (health score, drop reasons, fixes applied)
8. End-to-end loading with generated sample data files
"""

import io
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    raise SystemExit(
        "\n❌ pandas is not installed. Please install project dependencies first:\n"
        "   pip install -r requirements.txt\n"
    )

from modules.data_loader import (
    DataLoader,
    DataQualityReport,
    _clean_numeric_cell,
    _normalize_string,
    _parse_dates_robust,
    load_and_clean_data,
    load_purchases,
    load_sales,
    load_stock,
)


class TestNumericCleaning(unittest.TestCase):
    """Tests cleaning text and messy formatting from numeric columns."""

    def test_units_and_text_removal(self):
        # Quantity with units
        val, fix = _clean_numeric_cell("100 pcs")
        self.assertEqual(val, 100.0)
        self.assertIn("100", fix)

        # Kilograms and decimals
        val, _ = _clean_numeric_cell("45.5 kg")
        self.assertEqual(val, 45.5)

        # Approximate prefix
        val, _ = _clean_numeric_cell("~75 units")
        self.assertEqual(val, 75.0)
        val, _ = _clean_numeric_cell("approx 120")
        self.assertEqual(val, 120.0)

    def test_currency_and_commas(self):
        # Indian Rupee symbol & comma separator
        val, _ = _clean_numeric_cell("₹ 4,500.50")
        self.assertEqual(val, 4500.50)

        # Rs notation
        val, _ = _clean_numeric_cell("Rs. 1,250")
        self.assertEqual(val, 1250.0)

    def test_accounting_negatives(self):
        # Parentheses denote negative in accounting
        val, _ = _clean_numeric_cell("(50)")
        self.assertEqual(val, -50.0)

        val, _ = _clean_numeric_cell("-25.5")
        self.assertEqual(val, -25.5)

    def test_null_coercion(self):
        # N/A and placeholders coerced to None
        for placeholder in ["N/A", "na", "null", "-", "--", "None", "nil", ""]:
            val, _ = _clean_numeric_cell(placeholder)
            self.assertIsNone(val)


class TestDateParsing(unittest.TestCase):
    """Tests parsing diverse date formats common in Indian SMEs."""

    def test_dd_mm_yyyy_primary(self):
        series = pd.Series(["25/12/2024", "15-08-2025", "01/01/2026"])
        parsed, success, fails = _parse_dates_robust(series, prefer_dayfirst=True)
        self.assertEqual(fails, 0)
        self.assertEqual(success, 3)
        self.assertEqual(parsed.iloc[0].day, 25)
        self.assertEqual(parsed.iloc[0].month, 12)
        self.assertEqual(parsed.iloc[1].day, 15)
        self.assertEqual(parsed.iloc[1].month, 8)

    def test_iso_and_us_formats(self):
        series = pd.Series(["2025-04-14", "10/24/2024"])  # 24 is day, so 10 must be month
        parsed, success, fails = _parse_dates_robust(series, prefer_dayfirst=True)
        self.assertEqual(fails, 0)
        self.assertEqual(parsed.iloc[0], pd.Timestamp(2025, 4, 14))
        self.assertEqual(parsed.iloc[1], pd.Timestamp(2024, 10, 24))

    def test_excel_numeric_serial_dates(self):
        # Excel serial 45220 is ~ 2023-10-21
        series = pd.Series([45220, "45221"])
        parsed, success, fails = _parse_dates_robust(series)
        self.assertEqual(fails, 0)
        self.assertEqual(parsed.iloc[0].year, 2023)

    def test_invalid_dates(self):
        series = pd.Series(["not-a-date", "", "2025-02-31"])
        parsed, success, fails = _parse_dates_robust(series)
        self.assertTrue(parsed.iloc[0] is pd.NaT or pd.isna(parsed.iloc[0]))


class TestFuzzyColumnMapping(unittest.TestCase):
    """Tests fuzzy column name detection and Hindi alias support."""

    def setUp(self):
        self.loader = DataLoader(fuzzy_threshold=0.65)

    def test_hindi_and_messy_sales_columns(self):
        raw_cols = [
            "  Date (दिनांक)  ",
            "Product_Code / SKU",
            "Product Name (विवरण)",
            "Qty. (मात्रा)",
            "Customer / Party Name  ",
        ]
        mapping, unmapped, missing = self.loader.map_columns(raw_cols, "sales")
        self.assertEqual(mapping["  Date (दिनांक)  "], "date")
        self.assertEqual(mapping["Product_Code / SKU"], "product_id")
        self.assertEqual(mapping["Product Name (विवरण)"], "product_name")
        self.assertEqual(mapping["Qty. (मात्रा)"], "quantity")
        self.assertEqual(mapping["Customer / Party Name  "], "customer")
        self.assertEqual(len(missing), 0)

    def test_purchases_column_aliases(self):
        raw_cols = ["Voucher Tarikh", "RM Code", "Item Description", "Qnty", "Vendor Name", "TAT (Days)"]
        mapping, unmapped, missing = self.loader.map_columns(raw_cols, "purchases")
        self.assertEqual(mapping["Voucher Tarikh"], "date")
        self.assertEqual(mapping["RM Code"], "material_id")
        self.assertEqual(mapping["Item Description"], "material_name")
        self.assertEqual(mapping["Qnty"], "quantity")
        self.assertEqual(mapping["Vendor Name"], "supplier")
        self.assertEqual(mapping["TAT (Days)"], "lead_time_days")
        self.assertEqual(len(missing), 0)

    def test_stock_column_aliases(self):
        raw_cols = ["Item Code", "Particulars", "प्रकार", "Closing Stock", "UOM", "Last Sale Date", "Rate (₹)"]
        mapping, unmapped, missing = self.loader.map_columns(raw_cols, "stock")
        self.assertEqual(mapping["Item Code"], "item_id")
        self.assertEqual(mapping["Particulars"], "item_name")
        self.assertEqual(mapping["प्रकार"], "type")
        self.assertEqual(mapping["Closing Stock"], "current_qty")
        self.assertEqual(mapping["UOM"], "unit")
        self.assertEqual(mapping["Last Sale Date"], "last_movement_date")
        self.assertEqual(mapping["Rate (₹)"], "unit_cost")
        self.assertEqual(len(missing), 0)

    def test_auto_detect_dataset_type(self):
        sales_cols = ["Bill Date", "Cust Name", "Product ID", "Quantity"]
        purch_cols = ["Purchase Date", "Supplier", "Material Code", "Qty"]
        stock_cols = ["SKU", "Item Name", "Current Stock (Godam)", "Cost Price"]

        self.assertEqual(self.loader.detect_dataset_type(sales_cols), "sales")
        self.assertEqual(self.loader.detect_dataset_type(purch_cols), "purchases")
        self.assertEqual(self.loader.detect_dataset_type(stock_cols), "stock")


class TestDataLoaderPipeline(unittest.TestCase):
    """Tests the full loading, cleaning, deduplication, and reporting pipeline."""

    def test_in_memory_csv_cleaning(self):
        csv_data = (
            "  Date (दिनांक)  ,Product Code,Qty (मात्रा),Party\n"
            "15/01/2025,PRD-01,100 pcs,Bajaj Electricals\n"
            "15/01/2025,PRD-01,100 pcs,Bajaj Electricals\n"  # Duplicate
            "16/01/2025,PRD-02,  250  ,Havells Tier-2\n"
            "17/01/2025,PRD-03,₹ 500,Gupta Switchgear\n"
            ",PRD-04,50,Missing Date Party\n"  # Missing date
            "18/01/2025,,30,Missing SKU\n"  # Missing product ID
            ",,,\n"  # Completely empty row
        )
        buffer = io.BytesIO(csv_data.encode("utf-8"))
        df, report = load_and_clean_data(buffer, dataset_type="sales")

        # 7 rows initial -> 1 duplicate + 1 missing date + 1 missing SKU + 1 empty dropped -> 3 clean rows
        self.assertEqual(len(df), 3)
        self.assertEqual(report.rows_dropped, 4)
        self.assertIn("Duplicate rows", report.drop_reasons)
        self.assertIn("quantity", df.columns)
        self.assertIn("date", df.columns)

        # Quantity parsed as clean numbers
        self.assertEqual(df["quantity"].iloc[0], 100.0)
        self.assertEqual(df["quantity"].iloc[1], 250.0)
        self.assertEqual(df["quantity"].iloc[2], 500.0)

        # Dates parsed as datetime
        self.assertEqual(df["date"].iloc[0], pd.Timestamp(2025, 1, 15))

        # Health score should be reasonable
        self.assertGreater(report.health_score, 40.0)
        self.assertIn("Godam AI Data Quality Report", report.summary())

    def test_load_sample_files(self):
        """End-to-end integration test with the generated sample data."""
        sample_dir = Path(__file__).resolve().parent.parent / "sample_data"
        sales_file = sample_dir / "sales.csv"
        purchases_file = sample_dir / "purchases.csv"
        stock_file = sample_dir / "stock.csv"

        if not sales_file.exists():
            from sample_data.generate import generate_sample_data
            generate_sample_data(str(sample_dir))

        # 1. Test sales
        sales_df, sales_report = load_sales(sales_file)
        self.assertGreater(len(sales_df), 1000)
        self.assertEqual(set(sales_df.columns), {"date", "product_id", "product_name", "quantity", "customer"})
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(sales_df["date"]))
        self.assertTrue(pd.api.types.is_float_dtype(sales_df["quantity"]))
        self.assertGreater(sales_report.health_score, 80.0)

        # 2. Test purchases
        purch_df, purch_report = load_purchases(purchases_file)
        self.assertGreater(len(purch_df), 200)
        self.assertIn("lead_time_days", purch_df.columns)
        self.assertTrue(pd.api.types.is_float_dtype(purch_df["lead_time_days"]))

        # 3. Test stock
        stock_df, stock_report = load_stock(stock_file)
        self.assertGreater(len(stock_df), 5)
        self.assertIn("current_qty", stock_df.columns)
        self.assertIn("unit_cost", stock_df.columns)
        self.assertTrue(pd.api.types.is_float_dtype(stock_df["current_qty"]))


if __name__ == "__main__":
    unittest.main()

