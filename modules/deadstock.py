"""Godam AI - Deadstock & Working Capital Optimization Module
"Aapka godam, ab smart."

Key Capabilities:
1. Inactivity & Slow-Mover Detection:
   - Flags items with no sales or procurement movement for 90+ days (configurable).
   - Categorizes inventory into aging brackets:
     - Active (<= 90 days)
     - At Risk (91 - 180 days)
     - Slow Moving (181 - 365 days)
     - Deadstock (> 365 days)
2. Working Capital Lockup Calculation:
   - Rupee Value Locked: Current Qty * Unit Cost (₹).
   - Annual Carrying Cost Burden: ~20% per year (interest, godown space, insurance, deterioration).
3. Liquidation & Recovery Action Plan:
   - Returns ranked list sorted by locked capital (highest financial impact first).
   - Tailored SME recommendations (vendor returns, bundling discounts, scrap/melt recovery).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import numpy as np
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    np = None
    pd = None
    PANDAS_AVAILABLE = False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DeadstockItem:
    """Detailed financial and aging profile of an inactive or slow-moving SKU."""
    item_id: str
    item_name: str
    item_type: str  # "raw" or "finished"
    current_qty: float
    unit: str
    unit_cost: float
    cash_locked_rupees: float
    last_movement_date: Optional[datetime]
    days_inactive: int
    aging_bracket: str
    annual_carrying_cost: float
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert item to dictionary for tabular display or export."""
        return {
            "Item ID": self.item_id,
            "Item Name": self.item_name,
            "Type": self.item_type.capitalize(),
            "Current Qty": f"{self.current_qty:,.1f} {self.unit}",
            "Unit Cost": f"₹ {self.unit_cost:,.2f}",
            "Cash Locked (₹)": round(self.cash_locked_rupees, 2),
            "Days Inactive": self.days_inactive,
            "Last Movement": self.last_movement_date.strftime("%d %b %Y") if self.last_movement_date else "Unknown",
            "Aging Bracket": self.aging_bracket,
            "Carrying Cost/Yr (₹)": round(self.annual_carrying_cost, 2),
            "Action Plan": self.recommendation,
        }


@dataclass
class DeadstockReport:
    """Executive portfolio diagnostic on godam working capital and locked funds."""
    total_inventory_items: int
    total_inventory_value_rupees: float
    deadstock_items_count: int
    total_cash_locked_rupees: float
    deadstock_share_percentage: float
    annual_carrying_loss_rupees: float
    ranked_deadstock_items: List[DeadstockItem]
    aging_summary_df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame() if PANDAS_AVAILABLE else None)

    def summary(self) -> str:
        """Formatted executive summary in plain language."""
        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Godam AI Working Capital & Deadstock Diagnostic",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"• Total Inventory Value: ₹ {self.total_inventory_value_rupees:,.2f} across {self.total_inventory_items} SKUs",
            f"• Capital Locked in Deadstock: ₹ {self.total_cash_locked_rupees:,.2f} ({self.deadstock_share_percentage:.1f}% of total stock)",
            f"• Inactive / Slow SKUs: {self.deadstock_items_count} items",
            f"• Annual Carrying Cost Drain: ₹ {self.annual_carrying_loss_rupees:,.2f}/yr (interest + godown rent)",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Top Capital Recovery Opportunities (Ranked by Locked Cash):",
        ]

        for i, item in enumerate(self.ranked_deadstock_items[:5], 1):
            lines.append(
                f"  {i}. {item.item_name} ({item.item_id}) — ₹ {item.cash_locked_rupees:,.2f} locked "
                f"({item.days_inactive} days idle) | Action: {item.recommendation}"
            )

        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


# =============================================================================
# DEADSTOCK FORMULAS & CLASSIFICATION
# =============================================================================

def calculate_cash_locked(current_qty: float, unit_cost: float) -> float:
    """
    FORMULA: Rupee Value Locked
    ---------------------------
    Cash Locked = Current Quantity * Unit Cost (₹)

    Plain Language Explanation:
    - This is the exact amount of factory working capital frozen inside the godam.
    - Cash locked in non-moving items cannot be used to pay workers, purchase fast-moving raw materials,
      or clear supplier credit.
    """
    return max(0.0, float(current_qty) * float(unit_cost))


def calculate_annual_carrying_cost(cash_locked: float, carrying_rate: float = 0.20) -> float:
    """
    FORMULA: Annual Carrying Cost Drain
    -----------------------------------
    Carrying Cost = Cash Locked * Annual Carrying Rate (~20%)

    Plain Language Explanation:
    - Holding inventory is not free. In Indian manufacturing, the annual cost of holding idle stock includes:
      1. Bank Working Capital Interest / Cash Credit (CC) limit interest: 9% - 12%
      2. Godam space, rent, security, lighting: 4% - 6%
      3. Pilferage, dust, oxidation, scrap loss, insurance: 3% - 4%
      Total holding drain = ~20% of locked value every year.
    """
    return max(0.0, float(cash_locked) * float(carrying_rate))


def determine_aging_bracket(days_inactive: int) -> str:
    """Categorizes inactive inventory into standard manufacturing aging buckets."""
    if days_inactive <= 90:
        return "Active (<=90d)"
    elif days_inactive <= 180:
        return "At Risk (91-180d)"
    elif days_inactive <= 365:
        return "Slow Moving (181-365d)"
    else:
        return "Deadstock (>365d)"


def generate_sme_recommendation(
    item_type: str,
    days_inactive: int,
    cash_locked: float,
    item_name: str,
) -> str:
    """
    Provides practical, context-aware liquidation recommendations
    tailored for Indian SME manufacturing factories.
    """
    name_lower = item_name.lower()

    if days_inactive > 365:
        if "copper" in name_lower or "brass" in name_lower or "metal" in name_lower:
            return "Scrap / melt recovery (recover 65-75% metal market value immediately)"
        elif item_type.lower() == "raw":
            return "Negotiate vendor buyback at 15-20% restocking fee or swap for active materials"
        else:
            return "Liquidate at clearance pricing (30-40% discount) to tier-2 wholesalers"

    elif days_inactive > 180:
        if item_type.lower() == "finished":
            return "Bundle with top-selling finished goods at promotional discount"
        else:
            return "Request supplier return for credit note against upcoming active raw material orders"

    else:  # 91 to 180 days (At Risk)
        if item_type.lower() == "finished":
            return "Prioritize sales pitch to existing corporate clients; halt future production batches"
        else:
            return "Freeze procurement immediately; re-evaluate BOM consumption schedule"


# =============================================================================
# DEADSTOCK ANALYZER ENGINE
# =============================================================================

class DeadstockAnalyzer:
    """
    Analyzes godam stock datasets, flags slow movers and deadstock,
    calculates locked working capital, and ranks liquidation priorities.
    """

    def __init__(
        self,
        inactivity_threshold_days: int = 90,
        annual_carrying_rate: float = 0.20,
    ):
        self.inactivity_threshold_days = inactivity_threshold_days
        self.annual_carrying_rate = annual_carrying_rate

    def reconcile_last_movement_dates(
        self,
        stock_df: pd.DataFrame,
        sales_df: Optional[pd.DataFrame] = None,
        purchases_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, datetime]:
        """
        Reconciles the true last movement date by cross-referencing stock ledger
        with actual dispatch dates (from sales) and intake dates (from purchases).
        """
        reconciled: Dict[str, datetime] = {}

        # 1. Start with last_movement_date from stock.csv if present
        if "last_movement_date" in stock_df.columns:
            for _, row in stock_df.iterrows():
                iid = str(row["item_id"])
                dt = row["last_movement_date"]
                if pd.notna(dt):
                    try:
                        reconciled[iid] = pd.to_datetime(dt)
                    except Exception:
                        pass

        # 2. Cross-reference latest sale date for finished goods
        if sales_df is not None and not sales_df.empty and "date" in sales_df.columns and "product_id" in sales_df.columns:
            sales_clean = sales_df.dropna(subset=["date", "product_id"])
            for pid, group in sales_clean.groupby("product_id"):
                pid_str = str(pid)
                latest_sale = pd.to_datetime(group["date"]).max()
                if pid_str in reconciled:
                    reconciled[pid_str] = max(reconciled[pid_str], latest_sale)
                else:
                    reconciled[pid_str] = latest_sale

        # 3. Cross-reference latest purchase date for raw materials
        if purchases_df is not None and not purchases_df.empty and "date" in purchases_df.columns and "material_id" in purchases_df.columns:
            purch_clean = purchases_df.dropna(subset=["date", "material_id"])
            for mid, group in purch_clean.groupby("material_id"):
                mid_str = str(mid)
                latest_purch = pd.to_datetime(group["date"]).max()
                if mid_str in reconciled:
                    reconciled[mid_str] = max(reconciled[mid_str], latest_purch)
                else:
                    reconciled[mid_str] = latest_purch

        return reconciled

    def analyze_inventory(
        self,
        stock_df: pd.DataFrame,
        sales_df: Optional[pd.DataFrame] = None,
        purchases_df: Optional[pd.DataFrame] = None,
        inactivity_threshold_days: Optional[int] = None,
        reference_date: Optional[datetime] = None,
    ) -> DeadstockReport:
        """
        Executes complete deadstock & working capital analysis.

        Parameters:
            stock_df: Clean stock DataFrame (item_id, item_name, type, current_qty, unit_cost, last_movement_date)
            sales_df: Optional clean sales transactions
            purchases_df: Optional clean procurement transactions
            inactivity_threshold_days: Minimum idle days to flag (default 90)
            reference_date: "Today" date for aging calculation (defaults to dataset max date or system now)

        Returns:
            DeadstockReport with ranked items and financial summaries.
        """
        # Guard: None or empty stock → return blank report immediately
        if stock_df is None or (isinstance(stock_df, pd.DataFrame) and stock_df.empty):
            return DeadstockReport(
                total_inventory_items=0,
                total_inventory_value_rupees=0.0,
                deadstock_items_count=0,
                total_cash_locked_rupees=0.0,
                deadstock_share_percentage=0.0,
                annual_carrying_loss_rupees=0.0,
                ranked_deadstock_items=[],
            )

        # Guard: missing required column → return blank report with a note
        if "item_id" not in stock_df.columns:
            return DeadstockReport(
                total_inventory_items=0,
                total_inventory_value_rupees=0.0,
                deadstock_items_count=0,
                total_cash_locked_rupees=0.0,
                deadstock_share_percentage=0.0,
                annual_carrying_loss_rupees=0.0,
                ranked_deadstock_items=[],
            )

        threshold = inactivity_threshold_days if inactivity_threshold_days is not None else self.inactivity_threshold_days

        # Determine reference date
        if reference_date is None:
            # Anchor to latest date across datasets
            dates = []
            if "last_movement_date" in stock_df.columns:
                valid_stock_dates = pd.to_datetime(stock_df["last_movement_date"], errors="coerce").dropna()
                if not valid_stock_dates.empty:
                    dates.append(valid_stock_dates.max())
            if sales_df is not None and "date" in sales_df.columns:
                valid_sales_dates = pd.to_datetime(sales_df["date"], errors="coerce").dropna()
                if not valid_sales_dates.empty:
                    dates.append(valid_sales_dates.max())
            reference_date = max(dates) if dates else datetime.now()

        # Reconcile movement dates
        movement_dates = self.reconcile_last_movement_dates(stock_df, sales_df, purchases_df)

        all_items_count = len(stock_df)
        total_inventory_val = 0.0
        deadstock_items: List[DeadstockItem] = []

        for _, row in stock_df.iterrows():
            item_id = str(row["item_id"])
            item_name = str(row.get("item_name", item_id))
            item_type = str(row.get("type", "raw")).lower()
            current_qty = float(row.get("current_qty", 0.0))
            unit = str(row.get("unit", "units"))
            unit_cost = float(row.get("unit_cost", 0.0))

            cash_locked = calculate_cash_locked(current_qty, unit_cost)
            total_inventory_val += cash_locked

            # Calculate days of inactivity
            mvt_date = movement_dates.get(item_id)
            if mvt_date is not None and pd.notna(mvt_date):
                days_idle = max(0, (reference_date - pd.to_datetime(mvt_date)).days)
            else:
                # Default to threshold if date missing but stock is present
                days_idle = threshold + 1
                mvt_date = None

            aging_bracket = determine_aging_bracket(days_idle)
            carrying_cost = calculate_annual_carrying_cost(cash_locked, self.annual_carrying_rate)

            # Flag if days_inactive >= threshold and stock > 0
            if days_idle >= threshold and current_qty > 0:
                rec = generate_sme_recommendation(
                    item_type=item_type,
                    days_inactive=days_idle,
                    cash_locked=cash_locked,
                    item_name=item_name,
                )
                deadstock_items.append(DeadstockItem(
                    item_id=item_id,
                    item_name=item_name,
                    item_type=item_type,
                    current_qty=current_qty,
                    unit=unit,
                    unit_cost=unit_cost,
                    cash_locked_rupees=cash_locked,
                    last_movement_date=mvt_date,
                    days_inactive=days_idle,
                    aging_bracket=aging_bracket,
                    annual_carrying_cost=carrying_cost,
                    recommendation=rec,
                ))

        # Sort deadstock items descending by cash locked (highest financial impact first)
        ranked_deadstock = sorted(deadstock_items, key=lambda x: x.cash_locked_rupees, reverse=True)

        total_deadstock_cash = sum(x.cash_locked_rupees for x in ranked_deadstock)
        total_carrying_drain = sum(x.annual_carrying_cost for x in ranked_deadstock)
        deadstock_share = (total_deadstock_cash / max(1e-4, total_inventory_val)) * 100.0

        # Build aging breakdown summary table
        aging_summary = self._build_aging_summary(stock_df, movement_dates, reference_date)

        return DeadstockReport(
            total_inventory_items=all_items_count,
            total_inventory_value_rupees=round(total_inventory_val, 2),
            deadstock_items_count=len(ranked_deadstock),
            total_cash_locked_rupees=round(total_deadstock_cash, 2),
            deadstock_share_percentage=round(deadstock_share, 1),
            annual_carrying_loss_rupees=round(total_carrying_drain, 2),
            ranked_deadstock_items=ranked_deadstock,
            aging_summary_df=aging_summary,
        )

    def _build_aging_summary(
        self,
        stock_df: pd.DataFrame,
        movement_dates: Dict[str, datetime],
        reference_date: datetime,
    ) -> pd.DataFrame:
        """Constructs an aging distribution table across all inventory items."""
        brackets = [
            "Active (<=90d)",
            "At Risk (91-180d)",
            "Slow Moving (181-365d)",
            "Deadstock (>365d)",
        ]
        counts = {b: 0 for b in brackets}
        values = {b: 0.0 for b in brackets}

        for _, row in stock_df.iterrows():
            item_id = str(row["item_id"])
            current_qty = float(row.get("current_qty", 0.0))
            unit_cost = float(row.get("unit_cost", 0.0))
            val = current_qty * unit_cost

            mvt_date = movement_dates.get(item_id)
            if mvt_date is not None and pd.notna(mvt_date):
                days_idle = max(0, (reference_date - pd.to_datetime(mvt_date)).days)
            else:
                days_idle = 0

            bracket = determine_aging_bracket(days_idle)
            counts[bracket] += 1
            values[bracket] += val

        total_val = sum(values.values())
        summary_rows = []
        for b in brackets:
            share = (values[b] / max(1e-4, total_val)) * 100.0
            summary_rows.append({
                "Aging Bracket": b,
                "SKU Count": counts[b],
                "Value Locked (₹)": round(values[b], 2),
                "Share of Stock %": f"{share:.1f}%",
                "Carrying Drain/Yr (₹)": round(values[b] * self.annual_carrying_rate, 2),
            })

        return pd.DataFrame(summary_rows)
