"""Godam AI - Unit & Integration Tests for Assistant and Report Modules
"Aapka godam, ab smart."

Tests cover:
1. Assistant context builder: excludes raw transaction data, aggregates computed metrics
2. Assistant guardrails: responds "Mere paas yeh data nahi hai" for unknown or out-of-context queries
3. Assistant domain answering: handles English and Hindi/Hinglish queries on reorders and dead stock
4. PDF Report Generator: generates a valid 1-page PDF document
"""

import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from modules.assistant import GodamAssistant, build_assistant_context
from modules.deadstock import DeadstockItem, DeadstockReport
from modules.inventory import InventoryAlert
from modules.report import ReportGenerator, _format_rs


class TestAssistantModule(unittest.TestCase):
    """Tests the natural language assistant logic and guardrails."""

    def setUp(self):
        # Create mock computed metrics (NO raw transaction rows)
        self.mock_deadstock_report = DeadstockReport(
            total_inventory_items=15,
            total_inventory_value_rupees=1250000.0,
            deadstock_items_count=2,
            total_cash_locked_rupees=332500.0,
            deadstock_share_percentage=26.6,
            annual_carrying_loss_rupees=66500.0,
            ranked_deadstock_items=[
                DeadstockItem(
                    item_id="RM-207",
                    item_name="Lead-Alloy Solder Wire",
                    item_type="raw",
                    current_qty=350.0,
                    unit="kg",
                    unit_cost=950.0,
                    cash_locked_rupees=332500.0,
                    last_movement_date=datetime(2025, 12, 20),
                    days_inactive=315,
                    aging_bracket="Slow Moving (181-365d)",
                    annual_carrying_cost=66500.0,
                    recommendation="Negotiate vendor buyback for credit note",
                )
            ],
        )

        self.mock_alerts = [
            InventoryAlert(
                material_id="RM-202",
                material_name="Electrolytic Copper Strip",
                urgency="Critical",
                recommended_qty=455.0,
                unit="kg",
                order_deadline=datetime(2026, 11, 5),
                stockout_date=datetime(2026, 11, 15),
                current_stock=416.0,
                reorder_point=685.0,
                alert_message="Order 455 kg of Electrolytic Copper Strip by Thursday, 05 Nov",
            )
        ]

        self.context = build_assistant_context(
            inventory_alerts=self.mock_alerts,
            deadstock_report=self.mock_deadstock_report,
            company_name="Shree Durga Industrial Components",
        )
        self.assistant = GodamAssistant()

    def test_context_excludes_raw_data(self):
        """Verifies that assistant context only contains computed metrics, not raw transaction logs."""
        self.assertIn("summary_metrics", self.context)
        self.assertIn("urgent_reorders", self.context)
        self.assertIn("top_deadstock_items", self.context)
        # Ensure no arbitrary raw tables are leaked
        self.assertNotIn("sales_rows", self.context)
        self.assertNotIn("purchases_rows", self.context)

    def test_guardrail_strictly_triggers_for_unknown_data(self):
        """Assistant MUST reply 'Mere paas yeh data nahi hai' when asked for unrecorded information."""
        # Query about employee salaries (not in inventory context)
        resp = self.assistant.ask("Factory ke workers ki salary kitni baki hai?", self.context)
        self.assertEqual(resp.strip(), "Mere paas yeh data nahi hai.")

        # Query about competitor market prices
        resp_comp = self.assistant.ask("China market me copper ka kya rate chal raha hai?", self.context)
        self.assertEqual(resp_comp.strip(), "Mere paas yeh data nahi hai.")

    def test_answers_reorder_query_in_hindi(self):
        """Assistant correctly answers 'Is hafte kya order karna hai?' using computed alerts."""
        query = "Is hafte kya order karna hai?"
        resp = self.assistant.ask(query, self.context)
        self.assertIn("Electrolytic Copper Strip", resp)
        self.assertIn("455", resp)

    def test_answers_deadstock_query_in_hindi(self):
        """Assistant correctly answers 'Kaun sa maal paisa phasa raha hai?'."""
        query = "Kaun sa maal paisa phasa raha hai?"
        resp = self.assistant.ask(query, self.context)
        self.assertTrue("3.33 Lakh" in resp or "3.32 Lakh" in resp or "332,500" in resp)
        self.assertIn("Lead-Alloy Solder Wire", resp)


class TestReportGenerator(unittest.TestCase):
    """Tests executive PDF report generation."""

    def test_pdf_generation(self):
        from modules.report import FPDF_AVAILABLE, ReportGenerator

        if not FPDF_AVAILABLE:
            self.skipTest("fpdf2 is not yet installed in the current environment.")

        # Setup mock report
        deadstock_report = DeadstockReport(
            total_inventory_items=15,
            total_inventory_value_rupees=1250000.0,
            deadstock_items_count=2,
            total_cash_locked_rupees=332500.0,
            deadstock_share_percentage=26.6,
            annual_carrying_loss_rupees=66500.0,
            ranked_deadstock_items=[],
        )

        pdf_bytes = ReportGenerator.generate_health_report_pdf(
            deadstock_report=deadstock_report,
            inventory_alerts=[],
            company_name="Shree Durga Industrial Components",
            audit_date=datetime(2026, 11, 1),
        )

        # Standard PDF files start with %PDF
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_currency_formatting(self):
        self.assertEqual(_format_rs(332500.0), "Rs. 3.33 Lakh")
        self.assertEqual(_format_rs(15000000.0), "Rs. 1.50 Cr")
        self.assertEqual(_format_rs(4500.0), "Rs. 4,500")


if __name__ == "__main__":
    unittest.main()
