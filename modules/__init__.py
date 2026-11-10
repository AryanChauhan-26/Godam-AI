"""Godam AI - Core Modules Package
"Aapka godam, ab smart."
"""

from .data_loader import (
    DataLoader,
    DataQualityReport,
    load_and_clean_data,
    load_purchases,
    load_sales,
    load_stock,
)
from .forecasting import (
    ProductForecastResult,
    aggregate_sales_to_weekly,
    calculate_wape,
    forecast_all_products,
    forecast_single_product,
    get_forecast_summary_table,
)
from .inventory import (
    InventoryAlert,
    InventoryOptimizer,
    MaterialInventoryMetrics,
    calculate_eoq,
    calculate_reorder_point,
    calculate_safety_stock,
    calculate_weeks_of_cover,
)
from .deadstock import (
    DeadstockAnalyzer,
    DeadstockItem,
    DeadstockReport,
    calculate_annual_carrying_cost,
    calculate_cash_locked,
    determine_aging_bracket,
)
from .assistant import (
    GodamAssistant,
    build_assistant_context,
)
from .report import (
    ReportGenerator,
)

__all__ = [
    # Data Layer
    "DataLoader",
    "DataQualityReport",
    "load_and_clean_data",
    "load_sales",
    "load_purchases",
    "load_stock",
    # Forecasting
    "ProductForecastResult",
    "aggregate_sales_to_weekly",
    "calculate_wape",
    "forecast_all_products",
    "forecast_single_product",
    "get_forecast_summary_table",
    # Inventory Optimization
    "InventoryOptimizer",
    "MaterialInventoryMetrics",
    "InventoryAlert",
    "calculate_safety_stock",
    "calculate_reorder_point",
    "calculate_eoq",
    "calculate_weeks_of_cover",
    # Deadstock & Working Capital
    "DeadstockAnalyzer",
    "DeadstockItem",
    "DeadstockReport",
    "calculate_cash_locked",
    "calculate_annual_carrying_cost",
    "determine_aging_bracket",
    # Assistant & Reports
    "GodamAssistant",
    "build_assistant_context",
    "ReportGenerator",
]
