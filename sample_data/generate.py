"""Godam AI - Sample Data Generator
"Aapka godam, ab smart."

Generates 24 months of realistic SME manufacturing data:
1. sales.csv: date, product_id, product_name, quantity, customer
2. purchases.csv: date, material_id, material_name, quantity, supplier, lead_time_days
3. stock.csv: item_id, item_name, type, current_qty, unit, last_movement_date, unit_cost

Includes:
- Indian manufacturing context (electrical & metal components)
- Diwali (Oct-Nov) and Holi (Mar) festival spikes
- Monsoon slowdown (Jul-Aug)
- Slow-moving / deadstock items (no movement in 6-12 months)
- Messy data artifacts (Hindi/messy headers, text in numbers, mixed date formats, duplicates, missing values)
"""

import csv
import datetime
import math
import os
import random
from typing import Dict, List, Tuple


def generate_sample_data(output_dir: str = None) -> Dict[str, str]:
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)

    # Deterministic generation for reproducible test datasets
    random.seed(42)

    # 24-month date range: 2024-11-01 to 2026-10-31
    start_date = datetime.date(2024, 11, 1)
    end_date = datetime.date(2026, 10, 31)
    total_days = (end_date - start_date).days

    # =========================================================================
    # 1. CATALOG DEFINITION (Indian Electrical & Metal Fabrication Factory)
    # =========================================================================
    finished_goods = [
        {"id": "FG-101", "name": "Brass Terminal Connector 15A", "unit": "pcs", "cost": 18.5, "base_demand": 85, "variance": 20, "is_slow": False},
        {"id": "FG-102", "name": "Copper Busbar Link 200A", "unit": "pcs", "cost": 145.0, "base_demand": 35, "variance": 10, "is_slow": False},
        {"id": "FG-103", "name": "Mild Steel Enclosure Box 8x6", "unit": "pcs", "cost": 320.0, "base_demand": 25, "variance": 8, "is_slow": False},
        {"id": "FG-104", "name": "Bakelite Base Plate 4-Way", "unit": "pcs", "cost": 42.0, "base_demand": 110, "variance": 25, "is_slow": False},
        {"id": "FG-105", "name": "Rotary Cam Switch 32A", "unit": "pcs", "cost": 210.0, "base_demand": 40, "variance": 12, "is_slow": False},
        {"id": "FG-106", "name": "DIN Rail Mounting Channel 1m", "unit": "mtr", "cost": 55.0, "base_demand": 70, "variance": 15, "is_slow": False},
        {"id": "FG-107", "name": "Industrial Plug Socket 16A 3Pin", "unit": "pcs", "cost": 95.0, "base_demand": 60, "variance": 18, "is_slow": False},
        # Slow-moving / deadstock candidate:
        {"id": "FG-108", "name": "Legacy Bakelite Fuse Base 63A", "unit": "pcs", "cost": 120.0, "base_demand": 4, "variance": 2, "is_slow": True},
    ]

    raw_materials = [
        {"id": "RM-201", "name": "Free Cutting Brass Rod 12mm", "unit": "kg", "cost": 460.0, "base_lead_time": 7},
        {"id": "RM-202", "name": "Electrolytic Copper Strip 25x3", "unit": "kg", "cost": 780.0, "base_lead_time": 10},
        {"id": "RM-203", "name": "Cold Rolled Steel Sheet 1.2mm", "unit": "kg", "cost": 72.0, "base_lead_time": 14},
        {"id": "RM-204", "name": "Phenolic Bakelite Powder Grade B", "unit": "kg", "cost": 115.0, "base_lead_time": 5},
        {"id": "RM-205", "name": "Stainless Steel Fasteners M4x16", "unit": "kg", "cost": 230.0, "base_lead_time": 4},
        {"id": "RM-206", "name": "Zinc Electroplating Chemical", "unit": "ltr", "cost": 180.0, "base_lead_time": 6},
        # Slow-moving raw material (no purchase or movement in > 9 months):
        {"id": "RM-207", "name": "Lead-Alloy Solder Wire 60/40", "unit": "kg", "cost": 950.0, "base_lead_time": 12, "is_slow": True},
    ]

    customers = [
        "Bajaj Electricals Ancillary Hub",
        "Havells India Tier-2 Unit",
        "Gupta Switchgear Works, Delhi",
        "Laxmi Industrial Controls, Rajkot",
        "Mahindra Auto Electricals, Chakan",
        "Supertech Panels Pvt Ltd, Noida",
        "V-Guard Ancillary Supplier, Coimbatore",
        "Kiran Electricals, Ahmedabad",
        "Local Counter Cash Sales",
    ]

    suppliers = [
        "Hindalco Copper & Brass Distributors",
        "Tata Steel Service Center, Ludhiana",
        "National Fasteners & Hardware, Faridabad",
        "Kores Chemicals Industrial Ltd",
        "Shree Ganesh Metals, Jamnagar",
        "Apex Polymers & Resins, Vapi",
    ]

    # Helper function to get seasonal demand multiplier
    def get_seasonal_multiplier(date: datetime.date) -> float:
        month = date.month
        # Diwali spike: October - November (multiplier 2.0 to 2.8x)
        if month in (10, 11):
            return 2.2 + 0.4 * math.sin(date.day / 5.0)
        # Holi & FY-end rush: March (multiplier 1.5 to 1.8x)
        elif month == 3:
            return 1.6 + 0.2 * math.cos(date.day / 6.0)
        # Post-Diwali wedding/infrastructure season: December - January
        elif month in (12, 1):
            return 1.2
        # Monsoon slowdown: July - August (multiplier 0.65 to 0.75x)
        elif month in (7, 8):
            return 0.7
        return 1.0

    # Helper to introduce messy date formatting
    def format_messy_date(dt: datetime.date, format_choice: int) -> str:
        if format_choice == 0:
            return dt.strftime("%d/%m/%Y")  # 25/12/2024 (standard Indian format)
        elif format_choice == 1:
            return dt.strftime("%Y-%m-%d")  # 2024-12-25 (ISO)
        elif format_choice == 2:
            return dt.strftime("%d-%m-%Y")  # 25-12-2024
        elif format_choice == 3:
            return f"  {dt.strftime('%d/%m/%Y')}  "  # leading/trailing spaces
        elif format_choice == 4:
            # MM/DD/YYYY only when day <= 12 to test ambiguous date handling
            if dt.day <= 12:
                return dt.strftime("%m/%d/%Y")
            return dt.strftime("%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")

    # Helper to introduce messy numeric formatting
    def format_messy_number(val: float, unit: str, is_int: bool = True) -> str:
        r = random.random()
        num_str = str(int(round(val))) if is_int else f"{val:.2f}"
        if r < 0.70:
            return num_str
        elif r < 0.80:
            return f"{num_str} {unit}"  # e.g. "150 pcs", "45 kg"
        elif r < 0.88:
            return f" {num_str} "  # whitespace
        elif r < 0.94:
            # Indian / standard comma grouping: e.g. 1,200
            val_int = int(round(val))
            return f"{val_int:,}"
        elif r < 0.97:
            return f"~{num_str}"  # approx text
        else:
            return ""  # missing value

    # =========================================================================
    # 2. GENERATE SALES DATA (sales.csv)
    # =========================================================================
    # Messy header containing Hindi and mixed casing:
    # " Date (दिनांक) ", "Product_Code / SKU", "Product Name", "Qty. (मात्रा)", "Customer / Party"
    sales_rows: List[List[str]] = []
    sales_headers = [
        "  Date (दिनांक)  ",
        "Product_Code / SKU",
        "Product Name",
        "Qty. (मात्रा)",
        "Customer / Party Name  ",
    ]

    # Pre-compute last movement dates for stock reconciliation
    last_sale_dates = {fg["id"]: start_date for fg in finished_goods}

    curr_date = start_date
    while curr_date <= end_date:
        mult = get_seasonal_multiplier(curr_date)
        # Skip Sundays for typical factory sales dispatch
        if curr_date.weekday() != 6:
            for fg in finished_goods:
                if fg["is_slow"]:
                    # Slow item stopped selling 9 months before end_date
                    cutoff_date = end_date - datetime.timedelta(days=270)
                    if curr_date > cutoff_date:
                        continue
                    if random.random() > 0.88:  # very sparse
                        qty = max(1, int(random.gauss(fg["base_demand"], fg["variance"])))
                        cust = random.choice(customers)
                        date_fmt = random.randint(0, 4)
                        sales_rows.append([
                            format_messy_date(curr_date, date_fmt),
                            fg["id"],
                            fg["name"],
                            format_messy_number(qty, fg["unit"], is_int=True),
                            cust if random.random() > 0.05 else "",
                        ])
                        last_sale_dates[fg["id"]] = curr_date
                else:
                    # Regular items: frequency based on demand
                    if random.random() < 0.65:
                        base_qty = max(1, random.gauss(fg["base_demand"], fg["variance"]))
                        qty = max(1, int(round(base_qty * mult)))
                        cust = random.choice(customers)
                        date_fmt = random.randint(0, 4)
                        sales_rows.append([
                            format_messy_date(curr_date, date_fmt),
                            fg["id"],
                            fg["name"],
                            format_messy_number(qty, fg["unit"], is_int=True),
                            cust if random.random() > 0.04 else "",
                        ])
                        last_sale_dates[fg["id"]] = curr_date

        curr_date += datetime.timedelta(days=1)

    # Inject some duplicates to test deduplication
    dup_count = max(5, int(len(sales_rows) * 0.02))
    for _ in range(dup_count):
        idx = random.randint(0, len(sales_rows) - 1)
        sales_rows.append(list(sales_rows[idx]))

    # Inject a few invalid / blank dates
    sales_rows.append(["", "FG-101", "Brass Terminal Connector 15A", "45", "Gupta Switchgear Works, Delhi"])
    sales_rows.append(["InvalidDate", "FG-102", "Copper Busbar Link 200A", "20", "Havells India Tier-2 Unit"])

    sales_path = os.path.join(output_dir, "sales.csv")
    with open(sales_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(sales_headers)
        writer.writerows(sales_rows)

    # =========================================================================
    # 3. GENERATE PURCHASES DATA (purchases.csv)
    # =========================================================================
    # Messy header:
    # "Purchase Date", "Material_ID", "Material Description", "Quantity (मात्रा)", "Vendor / Supplier", "Lead Time [days]"
    purchases_rows: List[List[str]] = []
    purchases_headers = [
        "Purchase Date (दिनांक)",
        "Material_ID",
        "Material Description",
        "Quantity (मात्रा)",
        "Vendor / Supplier",
        "Lead Time [days]",
    ]

    last_purchase_dates = {rm["id"]: start_date for rm in raw_materials}

    curr_date = start_date
    while curr_date <= end_date:
        mult = get_seasonal_multiplier(curr_date)
        # Procurement happens on average 2-3 times a month per material
        for rm in raw_materials:
            if rm.get("is_slow", False):
                # Stopped procurement 10 months ago
                cutoff_date = end_date - datetime.timedelta(days=300)
                if curr_date > cutoff_date:
                    continue
                if random.random() < 0.08:
                    qty = random.randint(20, 80)
                    lead = rm["base_lead_time"] + random.randint(-2, 3)
                    supp = random.choice(suppliers)
                    purchases_rows.append([
                        format_messy_date(curr_date, random.randint(0, 3)),
                        rm["id"],
                        rm["name"],
                        format_messy_number(qty, rm["unit"], is_int=True),
                        supp,
                        f"{lead} days" if random.random() < 0.15 else str(lead),
                    ])
                    last_purchase_dates[rm["id"]] = curr_date
            else:
                if random.random() < 0.12:  # ~3.5 orders per month
                    base_lot = 150 if rm["unit"] == "kg" else 80
                    qty = int(round(base_lot * mult * random.uniform(0.8, 1.4)))
                    lead = max(2, rm["base_lead_time"] + random.randint(-3, 5))
                    supp = random.choice(suppliers)
                    purchases_rows.append([
                        format_messy_date(curr_date, random.randint(0, 4)),
                        rm["id"],
                        rm["name"],
                        format_messy_number(qty, rm["unit"], is_int=True),
                        supp if random.random() > 0.03 else "",
                        f"{lead} days" if random.random() < 0.20 else str(lead),
                    ])
                    last_purchase_dates[rm["id"]] = curr_date

        curr_date += datetime.timedelta(days=1)

    # Add duplicate purchases
    for _ in range(5):
        idx = random.randint(0, len(purchases_rows) - 1)
        purchases_rows.append(list(purchases_rows[idx]))

    purchases_path = os.path.join(output_dir, "purchases.csv")
    with open(purchases_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(purchases_headers)
        writer.writerows(purchases_rows)

    # =========================================================================
    # 4. GENERATE STOCK DATA (stock.csv)
    # =========================================================================
    # item_id, item_name, type (raw/finished), current_qty, unit, last_movement_date, unit_cost
    stock_headers = [
        "Item_Code / SKU",
        "Item Name (विवरण)",
        "Type (Raw/Finished)",
        "Current Qty (स्टॉक मात्रा)",
        "Unit (इकाई)",
        "Last Movement Date",
        "Unit Cost (₹ Rate)",
    ]

    stock_rows: List[List[str]] = []

    # Finished goods stock
    for fg in finished_goods:
        if fg["is_slow"]:
            # High stock lying idle for months with old last movement date
            cur_qty = 280  # high deadstock inventory
            mvt_date = last_sale_dates[fg["id"]]
        else:
            cur_qty = random.randint(40, 220)
            mvt_date = last_sale_dates[fg["id"]]

        cost_val = f"₹ {fg['cost']:.2f}" if random.random() < 0.3 else str(fg["cost"])
        qty_val = f"{cur_qty} {fg['unit']}" if random.random() < 0.25 else str(cur_qty)
        stock_rows.append([
            fg["id"],
            fg["name"],
            "finished",
            qty_val,
            fg["unit"],
            mvt_date.strftime("%d/%m/%Y"),
            cost_val,
        ])

    # Raw materials stock
    for rm in raw_materials:
        if rm.get("is_slow", False):
            cur_qty = 350  # obsolete stock sitting in godam
            mvt_date = last_purchase_dates[rm["id"]]
        else:
            cur_qty = random.randint(80, 500)
            mvt_date = last_purchase_dates[rm["id"]]

        cost_val = f"₹ {rm['cost']:.2f}" if random.random() < 0.3 else str(rm["cost"])
        qty_val = f"{cur_qty} {rm['unit']}" if random.random() < 0.25 else str(cur_qty)
        stock_rows.append([
            rm["id"],
            rm["name"],
            "raw",
            qty_val,
            rm["unit"],
            mvt_date.strftime("%d/%m/%Y"),
            cost_val,
        ])

    stock_path = os.path.join(output_dir, "stock.csv")
    with open(stock_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(stock_headers)
        writer.writerows(stock_rows)

    return {
        "sales": sales_path,
        "purchases": purchases_path,
        "stock": stock_path,
    }


if __name__ == "__main__":
    generated = generate_sample_data()
    print("Godam AI sample datasets successfully generated:")
    for key, path in generated.items():
        print(f"  - {key}: {path} ({os.path.getsize(path)} bytes)")

