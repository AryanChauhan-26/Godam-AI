"""Godam AI - Executive PDF Report Generator
"Aapka godam, ab smart."

Generates a crisp, one-page executive "Godam Health Report" in PDF format:
- Designed as a high-impact sales tool for first meetings with factory owners (Seth ji)
- Company name, audit date, and brand styling
- Key financial snapshot: Total stock, locked capital in dead stock, annual holding drain
- Top 5 stockout risks (preventing factory downtime)
- Top 5 slow-moving / dead stock items (cash recovery opportunities)
- 3 plain-language, high-ROI executive recommendations
- Strictly engineered to fit on a single A4 page
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF = None
    FPDF_AVAILABLE = False


def _format_rs(val: Optional[float]) -> str:
    """Formats currency as Rs. Lakhs or Crores using ASCII-safe characters for standard PDF fonts."""
    if val is None:
        return "Rs. 0"
    v = float(val)
    abs_v = abs(v)
    if abs_v >= 10000000:
        return f"Rs. {v / 10000000:.2f} Cr"
    elif abs_v >= 100000:
        return f"Rs. {v / 100000:.2f} Lakh"
    elif abs_v >= 1000:
        return f"Rs. {v:,.0f}"
    else:
        return f"Rs. {v:.1f}"


class SinglePagePDF(FPDF if FPDF is not None else object):
    """Custom FPDF layout configured strictly for a 1-page executive factory audit."""

    def __init__(self, company_name: str, audit_date: Optional[datetime] = None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.company_name = company_name
        self.audit_date = audit_date if audit_date else datetime.now()
        # Strictly disable auto page break so content never spills onto page 2
        self.set_auto_page_break(False)
        self.set_margins(left=10, top=8, right=10)


class ReportGenerator:
    """Produces the one-page PDF Godam Health Report."""

    @staticmethod
    def generate_health_report_pdf(
        deadstock_report: Any,
        inventory_alerts: List[Any],
        company_name: str = "Shree Durga Industrial Components Pvt. Ltd.",
        audit_date: Optional[datetime] = None,
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Builds the 1-page PDF Godam Health Report.
        Returns PDF bytes (and writes to output_path if provided).
        """
        if not FPDF_AVAILABLE:
            raise RuntimeError(
                "fpdf2 is required for PDF report generation. Please run: pip install fpdf2"
            )

        date_obj = audit_date if audit_date else datetime.now()
        pdf = SinglePagePDF(company_name=company_name, audit_date=date_obj)
        pdf.add_page()

        # Usable width = 190 mm (210 - 20)
        # Usable height = 280 mm (297 - 17)

        # ---------------------------------------------------------------------
        # 1. HEADER & BRANDING (Y: 8 to 28 mm)
        # ---------------------------------------------------------------------
        pdf.set_fill_color(30, 58, 138)  # Deep Factory Navy (#1E3A8A)
        pdf.rect(10, 8, 190, 22, style="F")

        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_xy(14, 11)
        pdf.cell(120, 6, company_name.upper(), new_x="RIGHT", new_y="TOP", align="L")

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_xy(140, 11)
        pdf.cell(56, 6, "GODAM HEALTH AUDIT", new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(254, 243, 199)  # Light Amber
        pdf.set_xy(14, 18)
        pdf.cell(120, 5, "Godam AI - 'Aapka godam, ab smart.' | Demand & Inventory Optimization", new_x="RIGHT", new_y="TOP", align="L")

        pdf.set_xy(140, 18)
        pdf.cell(56, 5, f"Date: {date_obj.strftime('%d %b %Y')}", new_x="LMARGIN", new_y="NEXT", align="R")

        # ---------------------------------------------------------------------
        # 2. FINANCIAL SNAPSHOT BANNER (Y: 33 to 53 mm)
        # ---------------------------------------------------------------------
        tot_val = getattr(deadstock_report, "total_inventory_value_rupees", 0.0)
        locked_val = getattr(deadstock_report, "total_cash_locked_rupees", 0.0)
        drain_val = getattr(deadstock_report, "annual_carrying_loss_rupees", 0.0)
        share_pct = getattr(deadstock_report, "deadstock_share_percentage", 0.0)

        box_w = 60.6
        box_y = 33

        # Box 1: Total Inventory Value
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(226, 232, 240)
        pdf.rect(10, box_y, box_w, 18, style="DF")
        pdf.set_text_color(100, 116, 139)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_xy(12, box_y + 2)
        pdf.cell(box_w - 4, 4, "TOTAL GODAM INVENTORY VALUE", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(15, 23, 42)
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.set_xy(12, box_y + 7.5)
        pdf.cell(box_w - 4, 7, _format_rs(tot_val), new_x="LMARGIN", new_y="NEXT")

        # Box 2: Capital Locked in Dead Stock
        bx2 = 10 + box_w + 4
        pdf.set_fill_color(254, 242, 242)  # Soft Red
        pdf.set_draw_color(239, 68, 68)
        pdf.rect(bx2, box_y, box_w, 18, style="DF")
        pdf.set_text_color(185, 28, 28)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_xy(bx2 + 2, box_y + 2)
        pdf.cell(box_w - 4, 4, f"CASH LOCKED IN DEAD STOCK ({share_pct:.1f}%)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(153, 27, 27)
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.set_xy(bx2 + 2, box_y + 7.5)
        pdf.cell(box_w - 4, 7, _format_rs(locked_val), new_x="LMARGIN", new_y="NEXT")

        # Box 3: Annual Carrying Cost Drain
        bx3 = bx2 + box_w + 4
        pdf.set_fill_color(255, 251, 235)  # Soft Amber
        pdf.set_draw_color(245, 158, 11)
        pdf.rect(bx3, box_y, box_w, 18, style="DF")
        pdf.set_text_color(180, 83, 9)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_xy(bx3 + 2, box_y + 2)
        pdf.cell(box_w - 4, 4, "ANNUAL HOLDING DRAIN (~20%/YR)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(146, 64, 14)
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.set_xy(bx3 + 2, box_y + 7.5)
        pdf.cell(box_w - 4, 7, f"{_format_rs(drain_val)} / year", new_x="LMARGIN", new_y="NEXT")

        # ---------------------------------------------------------------------
        # 3. SECTION: TOP 5 STOCKOUT RISKS (Y: 55 to 118 mm)
        # ---------------------------------------------------------------------
        curr_y = 55
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 58, 138)
        pdf.set_xy(10, curr_y)
        pdf.cell(190, 5, "1. TOP 5 PRODUCTION STOCKOUT RISKS (URGENT ORDERS NEEDED)", new_x="LMARGIN", new_y="NEXT")

        curr_y += 6
        # Table Header
        pdf.set_fill_color(226, 232, 240)
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_xy(10, curr_y)
        pdf.cell(62, 5.5, "Raw Material Name", border=1, fill=True)
        pdf.cell(24, 5.5, "Current Stock", border=1, fill=True, align="R")
        pdf.cell(24, 5.5, "Reorder Point", border=1, fill=True, align="R")
        pdf.cell(26, 5.5, "Order Qty", border=1, fill=True, align="R")
        pdf.cell(32, 5.5, "Order Deadline", border=1, fill=True, align="C")
        pdf.cell(22, 5.5, "Urgency", border=1, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        curr_y += 5.5
        pdf.set_font("Helvetica", "", 7.5)

        # Get top 5 stockout risks (Critical & Soon first)
        urgency_sort = {"Critical": 0, "Soon": 1, "OK": 2}
        sorted_alerts = sorted(inventory_alerts, key=lambda a: (urgency_sort.get(getattr(a, "urgency", "OK"), 3), getattr(a, "current_stock", 0.0)))[:5]

        for alert in sorted_alerts:
            pdf.set_xy(10, curr_y)
            name = getattr(alert, "material_name", "Material")[:32]
            stock_str = f"{int(round(getattr(alert, 'current_stock', 0.0))):,} {getattr(alert, 'unit', '')}"
            rop_str = f"{int(round(getattr(alert, 'reorder_point', 0.0))):,}"
            order_str = f"{int(round(getattr(alert, 'recommended_qty', 0.0))):,} {getattr(alert, 'unit', '')}"
            deadline = alert.order_deadline.strftime("%a, %d %b") if getattr(alert, "order_deadline", None) else "Immediate"
            urgency = getattr(alert, "urgency", "OK").upper()

            pdf.set_text_color(15, 23, 42)
            pdf.cell(62, 5.2, name, border="B")
            pdf.cell(24, 5.2, stock_str, border="B", align="R")
            pdf.cell(24, 5.2, rop_str, border="B", align="R")
            pdf.cell(26, 5.2, order_str, border="B", align="R")
            pdf.cell(32, 5.2, deadline, border="B", align="C")

            if urgency == "CRITICAL":
                pdf.set_text_color(185, 28, 28)
                pdf.set_font("Helvetica", "B", 7.5)
            elif urgency == "SOON":
                pdf.set_text_color(180, 83, 9)
                pdf.set_font("Helvetica", "B", 7.5)
            else:
                pdf.set_text_color(22, 101, 52)
                pdf.set_font("Helvetica", "", 7.5)

            pdf.cell(22, 5.2, urgency, border="B", align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 7.5)
            curr_y += 5.2

        # ---------------------------------------------------------------------
        # 4. SECTION: TOP 5 SLOW-MOVING / DEAD STOCK ITEMS (Y: 122 to 185 mm)
        # ---------------------------------------------------------------------
        curr_y += 3
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(185, 28, 28)
        pdf.set_xy(10, curr_y)
        pdf.cell(190, 5, "2. TOP 5 DEAD STOCK & CAPITAL LOCKUP PRIORITIES", new_x="LMARGIN", new_y="NEXT")

        curr_y += 6
        # Table Header
        pdf.set_fill_color(254, 226, 226)  # Soft Pink
        pdf.set_text_color(127, 29, 29)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_xy(10, curr_y)
        pdf.cell(56, 5.5, "Item Description", border=1, fill=True)
        pdf.cell(20, 5.5, "Idle Qty", border=1, fill=True, align="R")
        pdf.cell(22, 5.5, "Days Idle", border=1, fill=True, align="C")
        pdf.cell(28, 5.5, "Cash Locked", border=1, fill=True, align="R")
        pdf.cell(64, 5.5, "Recommended Liquidation Action Plan", border=1, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")

        curr_y += 5.5
        pdf.set_font("Helvetica", "", 7.5)

        ranked_items = getattr(deadstock_report, "ranked_deadstock_items", [])[:5]
        for it in ranked_items:
            pdf.set_xy(10, curr_y)
            iname = getattr(it, "item_name", "Item")[:28]
            qty_str = f"{int(round(getattr(it, 'current_qty', 0.0))):,} {getattr(it, 'unit', '')}"
            idle_str = f"{getattr(it, 'days_inactive', 0)} days"
            amt_str = _format_rs(getattr(it, "cash_locked_rupees", 0.0))
            action = getattr(it, "recommendation", "Review stock")[:42]

            pdf.set_text_color(15, 23, 42)
            pdf.cell(56, 5.2, iname, border="B")
            pdf.cell(20, 5.2, qty_str, border="B", align="R")
            pdf.cell(22, 5.2, idle_str, border="B", align="C")

            pdf.set_text_color(185, 28, 28)
            pdf.set_font("Helvetica", "B", 7.5)
            pdf.cell(28, 5.2, amt_str, border="B", align="R")

            pdf.set_text_color(51, 65, 85)
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(64, 5.2, action, border="B", align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 7.5)
            curr_y += 5.2

        # ---------------------------------------------------------------------
        # 5. SECTION: 3 EXECUTIVE SALES RECOMMENDATIONS (Y: 190 to 260 mm)
        # ---------------------------------------------------------------------
        curr_y += 3
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 58, 138)
        pdf.set_xy(10, curr_y)
        pdf.cell(190, 5, "3. STRATEGIC EXECUTIVE RECOMMENDATIONS (WORKING CAPITAL RECOVERY)", new_x="LMARGIN", new_y="NEXT")

        curr_y += 6

        # Recommendation 1: Capital Recovery
        rec1_title = f"1. Immediate Cash Release: Liquidate top dead items to recover {_format_rs(locked_val * 0.70)}"
        rec1_desc = (
            f"The godam currently holds {_format_rs(locked_val)} in non-moving stock. Executing vendor buybacks "
            f"and scrap recovery on top items (e.g. solder wire, legacy bases) will inject immediate liquidity back into operating cash."
        )

        # Recommendation 2: Zero Stockout Downtime
        urgent_count = len([a for a in inventory_alerts if getattr(a, "urgency", "") == "Critical"])
        rec2_title = f"2. Prevent Machine Idling: Issue purchase orders for {urgent_count} critical materials immediately"
        rec2_desc = (
            f"Copper and steel stock levels are running below safety buffer thresholds. Placing replenishment orders "
            f"strictly before the indicated order deadlines will ensure 100% factory uptime without emergency procurement surcharges."
        )

        # Recommendation 3: Automated Reordering Discipline
        rec3_title = "3. Replace Manual Excel Ledgers with Automated Godam AI ROP Discipline"
        rec3_desc = (
            "Transitioning from static monthly Excel registers to automated 8-week backtested demand forecasting "
            "will permanently prevent over-purchasing and eliminate recurring deadstock accumulation."
        )

        recs = [(rec1_title, rec1_desc), (rec2_title, rec2_desc), (rec3_title, rec3_desc)]

        for title, desc in recs:
            pdf.set_fill_color(248, 250, 252)
            pdf.set_draw_color(203, 213, 225)
            pdf.rect(10, curr_y, 190, 16.5, style="DF")

            pdf.set_text_color(30, 58, 138)
            pdf.set_font("Helvetica", "B", 7.8)
            pdf.set_xy(13, curr_y + 1.8)
            pdf.cell(184, 4.5, title, new_x="LMARGIN", new_y="NEXT")

            pdf.set_text_color(71, 85, 105)
            pdf.set_font("Helvetica", "", 7.2)
            pdf.set_xy(13, curr_y + 6.5)
            pdf.multi_cell(184, 4, desc)

            curr_y += 18.5

        # ---------------------------------------------------------------------
        # 6. FOOTER (Y: 275 to 285 mm)
        # ---------------------------------------------------------------------
        pdf.set_xy(10, 275)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(10, 274, 200, 274)

        pdf.set_text_color(148, 163, 184)
        pdf.set_font("Helvetica", "I", 7)
        pdf.cell(120, 5, "Generated automatically by Godam AI | Confidential & Proprietary for Factory Leadership", new_x="RIGHT", new_y="TOP")
        pdf.cell(70, 5, "Page 1 of 1 | www.godamai.in", new_x="LMARGIN", new_y="NEXT", align="R")

        pdf_bytes = bytes(pdf.output())

        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes
