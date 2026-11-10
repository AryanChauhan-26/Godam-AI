"""Godam AI - Inventory Optimization & Reorder Logic
"Aapka godam, ab smart."

Key Capabilities:
1. Reorder Point (ROP) & Safety Stock:
   - Accounts for both demand variability (σ_D) and supplier lead-time variability (σ_L).
   - Configurable service level (default 95% -> Z = 1.645).
2. Order Sizing:
   - Economic Order Quantity (EOQ): Balances purchase order administration cost vs godown holding cost.
   - Weeks-of-Cover Rule: Configurable target inventory weeks (default 4 weeks).
3. Urgency Alert System:
   - Projects exact stockout dates: Current Stock / Daily Demand.
   - Backtracks supplier lead time to provide order deadlines:
     "Order 500 kg of Material X by Thursday, 05 Nov or stock runs out on 15 Nov".
   - Ranks by urgency: Critical, Soon, OK.
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
# DEFAULT SME BILL OF MATERIALS (BOM) & SERVICE LEVEL Z-SCORES
# =============================================================================

# Standard Z-scores for Normal Distribution service levels
SERVICE_LEVEL_Z: Dict[float, float] = {
    0.80: 0.842,
    0.85: 1.036,
    0.90: 1.282,
    0.95: 1.645,  # Godam AI Default: 95% order fulfillment without stockout
    0.98: 2.054,
    0.99: 2.326,
}

# Default BOM for Indian Electrical & Metal Switchgear Components
# Maps Finished Good (FG) -> {Raw Material (RM): quantity consumed per unit}
DEFAULT_SME_BOM: Dict[str, Dict[str, float]] = {
    "FG-101": {"RM-201": 0.05, "RM-206": 0.01},           # Brass Terminal Pin -> Brass Rod + Plating
    "FG-102": {"RM-202": 0.18},                           # Copper Busbar -> Electrolytic Copper Strip
    "FG-103": {"RM-203": 1.25, "RM-205": 0.08},           # Enclosure Box -> CR Steel Sheet + Fasteners
    "FG-104": {"RM-204": 0.22},                           # Bakelite Base Plate -> Bakelite Powder
    "FG-105": {"RM-201": 0.03, "RM-204": 0.15, "RM-205": 0.04}, # Cam Switch -> Brass + Resin + Fasteners
    "FG-106": {"RM-203": 0.45, "RM-206": 0.02},           # DIN Rail Channel -> CR Steel + Plating
    "FG-107": {"RM-201": 0.04, "RM-204": 0.12},           # Industrial Plug -> Brass + Bakelite
    "FG-108": {"RM-207": 0.02, "RM-204": 0.09},           # Legacy Fuse Base -> Solder Wire + Bakelite
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MaterialInventoryMetrics:
    """Stores inventory calculation outputs for an individual raw material."""
    material_id: str
    material_name: str
    unit: str
    current_stock: float
    avg_weekly_demand: float
    avg_daily_demand: float
    demand_std_weekly: float
    lead_time_days: float
    lead_time_weeks: float
    lead_time_std_days: float
    service_level: float
    safety_stock: float
    reorder_point: float
    eoq: float
    weeks_of_cover_qty: float
    recommended_order_qty: float
    days_of_supply: float
    stockout_date: Optional[datetime]
    order_deadline_date: Optional[datetime]
    urgency: str  # "Critical", "Soon", "OK"
    unit_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for UI or reporting."""
        return {
            "material_id": self.material_id,
            "material_name": self.material_name,
            "unit": self.unit,
            "current_stock": round(self.current_stock, 1),
            "avg_weekly_demand": round(self.avg_weekly_demand, 1),
            "lead_time_days": round(self.lead_time_days, 1),
            "safety_stock": round(self.safety_stock, 1),
            "reorder_point": round(self.reorder_point, 1),
            "recommended_order_qty": round(self.recommended_order_qty, 1),
            "days_of_supply": round(self.days_of_supply, 1),
            "urgency": self.urgency,
            "stockout_date": self.stockout_date.strftime("%d %b %Y") if self.stockout_date else "N/A",
            "order_deadline": self.order_deadline_date.strftime("%a, %d %b %Y") if self.order_deadline_date else "N/A",
        }


@dataclass
class InventoryAlert:
    """Actionable alert for the factory manager."""
    material_id: str
    material_name: str
    urgency: str  # "Critical", "Soon", "OK"
    recommended_qty: float
    unit: str
    order_deadline: Optional[datetime]
    stockout_date: Optional[datetime]
    current_stock: float
    reorder_point: float
    alert_message: str

    def format_plain_english(self) -> str:
        """Formatted plain text alert."""
        icon = "🚨 [CRITICAL]" if self.urgency == "Critical" else ("⚠️ [SOON]" if self.urgency == "Soon" else "✅ [OK]")
        return f"{icon} {self.alert_message}"


# =============================================================================
# INVENTORY FORMULAS WITH PLAIN-LANGUAGE EXPLANATIONS
# =============================================================================

def get_z_score(service_level: float = 0.95) -> float:
    """Returns the normal distribution Z-score for a given service level."""
    # Find closest match if not exact
    closest = min(SERVICE_LEVEL_Z.keys(), key=lambda k: abs(k - service_level))
    return SERVICE_LEVEL_Z[closest]


def calculate_safety_stock(
    avg_weekly_demand: float,
    demand_std_weekly: float,
    lead_time_weeks: float,
    lead_time_std_weeks: float = 0.0,
    service_level: float = 0.95,
) -> float:
    """
    FORMULA: Safety Stock (SS)
    --------------------------
    SS = Z * sqrt( (Lead_Time * Demand_Std^2) + (Demand^2 * Lead_Time_Std^2) )

    Plain Language Explanation:
    - In an Indian factory, suppliers often deliver a few days late (lead time variation),
      and factory customers place unpredictable orders (demand variation).
    - Safety Stock is the emergency buffer inventory kept in the godam so the factory
      never halts production during supply delays or sudden demand surges.
    - Z = factor corresponding to desired service level (e.g. 1.645 for 95% no-stockout guarantee).
    """
    z = get_z_score(service_level)
    variance_demand_part = lead_time_weeks * (demand_std_weekly ** 2)
    variance_lead_part = (avg_weekly_demand ** 2) * (lead_time_std_weeks ** 2)

    total_std = math.sqrt(max(0.0, variance_demand_part + variance_lead_part))
    return max(0.0, z * total_std)


def calculate_reorder_point(
    avg_weekly_demand: float,
    lead_time_weeks: float,
    safety_stock: float,
) -> float:
    """
    FORMULA: Reorder Point (ROP)
    ----------------------------
    ROP = (Average Weekly Demand * Lead Time in Weeks) + Safety Stock

    Plain Language Explanation:
    - This is the minimum stock level that triggers a new purchase order.
    - It ensures that while the supplier is manufacturing and transporting the raw material
      (the lead time), the factory has enough stock to keep running plus safety cushion.
    - When godam inventory drops to or below ROP, order immediately!
    """
    demand_during_lead_time = avg_weekly_demand * lead_time_weeks
    return max(0.0, demand_during_lead_time + safety_stock)


def calculate_eoq(
    annual_demand: float,
    order_cost: float = 500.0,
    unit_cost: float = 100.0,
    holding_cost_rate: float = 0.20,
) -> float:
    """
    FORMULA: Economic Order Quantity (EOQ)
    --------------------------------------
    EOQ = sqrt( (2 * Annual_Demand * Order_Cost) / (Holding_Cost_per_unit) )

    Plain Language Explanation:
    - Placing many small orders costs administrative paperwork, phone calls, and freight charges (Order Cost S).
    - But holding huge piles of inventory locks up working capital and godam space (Holding Cost H, ~20% of unit price per year).
    - EOQ calculates the exact order size that minimizes total inventory costs for the factory.
    """
    if annual_demand <= 0.0 or unit_cost <= 0.0:
        return 0.0

    holding_cost_per_unit = max(1e-4, holding_cost_rate * unit_cost)
    eoq = math.sqrt((2.0 * annual_demand * order_cost) / holding_cost_per_unit)
    return max(0.0, eoq)


def calculate_weeks_of_cover(
    avg_weekly_demand: float,
    target_weeks: float = 4.0,
) -> float:
    """
    FORMULA: Weeks-of-Cover Rule
    ----------------------------
    Recommended Quantity = Target Weeks * Average Weekly Demand

    Plain Language Explanation:
    - Many small factory owners prefer simple rules like "Always order 4 weeks worth of raw material".
    - This provides a pragmatic, intuitive order quantity benchmark.
    """
    return max(0.0, avg_weekly_demand * target_weeks)


# =============================================================================
# INVENTORY OPTIMIZER ENGINE
# =============================================================================

class InventoryOptimizer:
    """
    Main engine: Integrates forecasts, supplier lead times, and current stock
    to compute ROP, Safety Stock, EOQ, and prioritized urgency alerts.
    """

    def __init__(
        self,
        service_level: float = 0.95,
        default_lead_time_days: float = 7.0,
        order_cost_rupees: float = 500.0,
        holding_rate: float = 0.20,
        weeks_of_cover_target: float = 4.0,
        bom: Optional[Dict[str, Dict[str, float]]] = None,
    ):
        self.service_level = service_level
        self.default_lead_time_days = default_lead_time_days
        self.order_cost_rupees = order_cost_rupees
        self.holding_rate = holding_rate
        self.weeks_of_cover_target = weeks_of_cover_target
        self.bom = bom if bom is not None else DEFAULT_SME_BOM

    def compute_supplier_lead_times(
        self,
        purchases_df: pd.DataFrame,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Calculates mean and standard deviation of supplier lead times per material
        from historical procurement records.
        """
        lead_times: Dict[str, Tuple[float, float]] = {}

        if purchases_df.empty or "material_id" not in purchases_df.columns:
            return lead_times

        lt_col = next((c for c in ["lead_time_days", "lead_time"] if c in purchases_df.columns), None)

        for mid, group in purchases_df.groupby("material_id"):
            mid_str = str(mid)
            if lt_col and not group[lt_col].dropna().empty:
                valid_lts = pd.to_numeric(group[lt_col], errors="coerce").dropna().values
                if len(valid_lts) > 0:
                    mean_lt = float(np.mean(valid_lts))
                    std_lt = float(np.std(valid_lts)) if len(valid_lts) > 1 else 1.0
                    lead_times[mid_str] = (mean_lt, std_lt)
                    continue

            # Fallback default
            lead_times[mid_str] = (self.default_lead_time_days, 1.0)

        return lead_times

    def derive_raw_material_demands(
        self,
        product_forecasts: Dict[str, Any],  # maps product_id -> ProductForecastResult or dict
        purchases_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Tuple[float, float]]:
        """
        Calculates expected weekly demand and demand variability for each raw material.
        Uses Bill of Materials (BOM) explosion from finished goods forecasts:
        Material Demand = sum_FG( FG_Forecast * BOM_ratio )
        """
        material_weekly_series: Dict[str, List[float]] = {}

        # 1. Explode through BOM if forecasts are present
        if product_forecasts:
            for pid, res in product_forecasts.items():
                # Extract weekly forecast series
                if hasattr(res, "forecast_df"):
                    fg_forecasts = res.forecast_df["forecast"].values
                elif isinstance(res, dict) and "forecast_df" in res:
                    fg_forecasts = res["forecast_df"]["forecast"].values
                else:
                    continue

                bom_entries = self.bom.get(pid, {})
                for mid, ratio in bom_entries.items():
                    if mid not in material_weekly_series:
                        material_weekly_series[mid] = [0.0] * len(fg_forecasts)

                    for i, val in enumerate(fg_forecasts):
                        material_weekly_series[mid][i] += float(val) * float(ratio)

        # 2. Fallback to purchases history if any material has 0 derived demand
        if purchases_df is not None and not purchases_df.empty and "material_id" in purchases_df.columns:
            for mid, group in purchases_df.groupby("material_id"):
                mid_str = str(mid)
                if mid_str not in material_weekly_series or sum(material_weekly_series[mid_str]) == 0.0:
                    # Estimate from purchase cadence
                    q_col = next((c for c in ["quantity", "qty"] if c in group.columns), None)
                    if q_col:
                        quantities = pd.to_numeric(group[q_col], errors="coerce").dropna().values
                        if len(quantities) > 0:
                            avg_purchase = float(np.mean(quantities))
                            # Assume ~2 purchases per month on average
                            est_weekly = avg_purchase / 2.0
                            material_weekly_series[mid_str] = [est_weekly] * 12

        # Compute (mean_weekly, std_weekly)
        material_stats: Dict[str, Tuple[float, float]] = {}
        for mid, series in material_weekly_series.items():
            arr = np.asarray(series, dtype=float)
            mean_d = float(np.mean(arr)) if len(arr) > 0 else 10.0
            std_d = float(np.std(arr)) if len(arr) > 1 else max(1.0, mean_d * 0.25)
            material_stats[mid] = (max(0.1, mean_d), max(0.1, std_d))

        return material_stats

    def optimize_material(
        self,
        material_id: str,
        material_name: str,
        unit: str,
        current_stock: float,
        unit_cost: float,
        avg_weekly_demand: float,
        demand_std_weekly: float,
        lead_time_days: float,
        lead_time_std_days: float = 1.0,
        current_date: Optional[datetime] = None,
    ) -> MaterialInventoryMetrics:
        """
        Computes all inventory metrics, stockout date, and order urgency for a single material.
        """
        if current_date is None:
            current_date = datetime.now()

        lead_time_weeks = max(0.1, lead_time_days / 7.0)
        lead_time_std_weeks = lead_time_std_days / 7.0
        avg_daily_demand = max(1e-4, avg_weekly_demand / 7.0)

        # 1. Safety Stock
        ss = calculate_safety_stock(
            avg_weekly_demand=avg_weekly_demand,
            demand_std_weekly=demand_std_weekly,
            lead_time_weeks=lead_time_weeks,
            lead_time_std_weeks=lead_time_std_weeks,
            service_level=self.service_level,
        )

        # 2. Reorder Point
        rop = calculate_reorder_point(
            avg_weekly_demand=avg_weekly_demand,
            lead_time_weeks=lead_time_weeks,
            safety_stock=ss,
        )

        # 3. Order Sizing
        annual_demand = avg_weekly_demand * 52.0
        eoq_qty = calculate_eoq(
            annual_demand=annual_demand,
            order_cost=self.order_cost_rupees,
            unit_cost=unit_cost,
            holding_cost_rate=self.holding_rate,
        )
        cover_qty = calculate_weeks_of_cover(
            avg_weekly_demand=avg_weekly_demand,
            target_weeks=self.weeks_of_cover_target,
        )
        # Recommend EOQ if realistic, else Weeks of Cover
        rec_order_qty = eoq_qty if eoq_qty > 0.0 else cover_qty

        # 4. Runout & Stockout Projection
        days_of_supply = max(0.0, current_stock / avg_daily_demand)
        clamped_supply_days = min(3650.0, days_of_supply)
        stockout_date = current_date + timedelta(days=clamped_supply_days)

        # Order deadline must allow for lead time: Stockout Date - Lead Time
        deadline_days = max(0.0, days_of_supply - lead_time_days)
        clamped_deadline_days = min(3650.0, deadline_days)
        order_deadline_date = current_date + timedelta(days=clamped_deadline_days)

        # 5. Urgency Classification
        # Critical: Stock <= ROP OR Days of supply <= Lead Time
        if current_stock <= rop or days_of_supply <= lead_time_days:
            urgency = "Critical"
        elif days_of_supply <= (1.5 * lead_time_days):
            urgency = "Soon"
        else:
            urgency = "OK"

        return MaterialInventoryMetrics(
            material_id=material_id,
            material_name=material_name,
            unit=unit,
            current_stock=current_stock,
            avg_weekly_demand=avg_weekly_demand,
            avg_daily_demand=avg_daily_demand,
            demand_std_weekly=demand_std_weekly,
            lead_time_days=lead_time_days,
            lead_time_weeks=lead_time_weeks,
            lead_time_std_days=lead_time_std_days,
            service_level=self.service_level,
            safety_stock=ss,
            reorder_point=rop,
            eoq=eoq_qty,
            weeks_of_cover_qty=cover_qty,
            recommended_order_qty=rec_order_qty,
            days_of_supply=days_of_supply,
            stockout_date=stockout_date,
            order_deadline_date=order_deadline_date,
            urgency=urgency,
            unit_cost=unit_cost,
        )

    def generate_alerts(
        self,
        metrics_list: List[MaterialInventoryMetrics],
    ) -> List[InventoryAlert]:
        """
        Creates plain-language, actionable alerts ranked by urgency:
        1. Critical: Stockout imminent or below ROP.
        2. Soon: Order deadline within 7-10 days.
        3. OK: Healthy inventory buffer.
        """
        alerts: List[InventoryAlert] = []

        # Sort: Critical first, then Soon, then OK
        urgency_rank = {"Critical": 0, "Soon": 1, "OK": 2}
        sorted_metrics = sorted(metrics_list, key=lambda m: (urgency_rank.get(m.urgency, 3), m.days_of_supply))

        for m in sorted_metrics:
            stockout_str = m.stockout_date.strftime("%d %b") if m.stockout_date else "soon"
            deadline_str = m.order_deadline_date.strftime("%A, %d %b") if m.order_deadline_date else "immediately"
            order_amount = int(round(m.recommended_order_qty))

            if m.urgency == "Critical":
                if m.current_stock <= 0:
                    msg = (
                        f"STOCKOUT: {m.material_name} is completely out of stock! "
                        f"Order {order_amount:,} {m.unit} immediately from supplier (Lead time: {int(m.lead_time_days)} days)."
                    )
                else:
                    msg = (
                        f"Order {order_amount:,} {m.unit} of {m.material_name} by {deadline_str} "
                        f"or stock runs out on {stockout_str} (Current stock: {int(m.current_stock):,} {m.unit}, ROP: {int(m.reorder_point):,} {m.unit})."
                    )
            elif m.urgency == "Soon":
                msg = (
                    f"Order {order_amount:,} {m.unit} of {m.material_name} by {deadline_str} "
                    f"to avoid dipping into safety stock on {stockout_str} ({int(m.days_of_supply)} days of supply left)."
                )
            else:
                msg = (
                    f"{m.material_name} has {int(m.days_of_supply)} days of supply ({int(m.current_stock):,} {m.unit} on hand). "
                    f"Inventory is healthy, next order expected around {deadline_str}."
                )

            alerts.append(InventoryAlert(
                material_id=m.material_id,
                material_name=m.material_name,
                urgency=m.urgency,
                recommended_qty=m.recommended_order_qty,
                unit=m.unit,
                order_deadline=m.order_deadline_date,
                stockout_date=m.stockout_date,
                current_stock=m.current_stock,
                reorder_point=m.reorder_point,
                alert_message=msg,
            ))

        return alerts

    def optimize_all(
        self,
        stock_df: pd.DataFrame,
        purchases_df: pd.DataFrame,
        product_forecasts: Dict[str, Any],
        current_date: Optional[datetime] = None,
    ) -> Tuple[pd.DataFrame, List[InventoryAlert]]:
        """
        Executes full inventory optimization across all raw materials in the godam.

        Returns:
            Tuple of (summary_dataframe, ranked_alerts_list)
        """
        if current_date is None:
            # Anchor to dataset's latest date if available
            if not purchases_df.empty and "date" in purchases_df.columns:
                current_date = pd.to_datetime(purchases_df["date"]).max()
            else:
                current_date = datetime.now()

        # 1. Calculate supplier lead times
        lead_time_stats = self.compute_supplier_lead_times(purchases_df)

        # 2. Derive material demands from FG forecasts
        material_demands = self.derive_raw_material_demands(product_forecasts, purchases_df)

        # 3. Filter raw materials from stock
        raw_stock = stock_df[stock_df["type"].astype(str).str.lower().str.contains("raw|rm")].copy()
        if raw_stock.empty:
            # If type not explicitly specified, take all stock items
            raw_stock = stock_df.copy()

        metrics_list: List[MaterialInventoryMetrics] = []

        for _, row in raw_stock.iterrows():
            mid = str(row["item_id"])
            mname = str(row.get("item_name", mid))
            unit = str(row.get("unit", "units"))
            c_qty = float(row.get("current_qty", 0.0))
            cost = float(row.get("unit_cost", 100.0))

            mean_d, std_d = material_demands.get(mid, (25.0, 5.0))
            mean_lt, std_lt = lead_time_stats.get(mid, (self.default_lead_time_days, 1.0))

            m_metrics = self.optimize_material(
                material_id=mid,
                material_name=mname,
                unit=unit,
                current_stock=c_qty,
                unit_cost=cost,
                avg_weekly_demand=mean_d,
                demand_std_weekly=std_d,
                lead_time_days=mean_lt,
                lead_time_std_days=std_lt,
                current_date=current_date,
            )
            metrics_list.append(m_metrics)

        # 4. Generate alerts
        alerts = self.generate_alerts(metrics_list)

        # 5. Format summary table
        summary_rows = [m.to_dict() for m in metrics_list]
        summary_df = pd.DataFrame(summary_rows)
        if not summary_df.empty:
            urgency_sort = {"Critical": 0, "Soon": 1, "OK": 2}
            summary_df["_sort"] = summary_df["urgency"].map(urgency_sort)
            summary_df = summary_df.sort_values(["_sort", "days_of_supply"]).drop(columns=["_sort"]).reset_index(drop=True)

        return summary_df, alerts
