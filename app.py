"""Godam AI - Main Streamlit Web Application
"Aapka godam, ab smart."

Full Production Dashboard for Indian SME Manufacturing Factory Owners:
- Minimal industrial aesthetic with rich navy & warm saffron accents
- Large readable numbers in Indian format (Lakh / Crore with ₹)
- 7 Dedicated Pages:
  1. 📁 Upload: Excel/CSV or sample data with data quality health report
  2. 📊 Overview: KPI cards, urgent POs, top liquidation priorities
  3. 📈 Forecast: SKU-level demand with 12W projections, festival spikes, and tournament scores
  4. 🚨 Reorder Alerts: Critical/Soon/OK ranking with 1-click Excel PO download
  5. 🛑 Dead Stock: Working capital locked, aging chart, and ranked liquidation plan
  6. 💬 Ask Godam AI: Natural language Q&A in English/Hindi (Anthropic Claude with guardrails)
  7. 📄 Health Report: One-page executive PDF report download for factory sales meetings
  8. ⚙️ Settings: Service levels, deadstock days, and bilingual language toggle
"""

import io
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from modules.data_loader import DataLoader, load_purchases, load_sales, load_stock
from modules.deadstock import DeadstockAnalyzer, DeadstockReport
from modules.forecasting import (
    forecast_all_products,
    get_forecast_summary_table,
)
from modules.inventory import InventoryOptimizer
from modules.assistant import GodamAssistant, build_assistant_context
from modules.report import ReportGenerator, FPDF_AVAILABLE

# =============================================================================
# 1. BRANDING, STYLING & NUMBER FORMATTING
# =============================================================================

st.set_page_config(
    page_title="Godam AI - Aapka godam, ab smart",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Theme: Clean minimal look, rich navy & industrial saffron accent, large readable fonts
st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1E3A8A;
        letter-spacing: -0.5px;
        margin-bottom: 0px;
    }
    .sub-tagline {
        font-size: 1.05rem;
        color: #B45309;
        font-weight: 600;
        margin-bottom: 1.2rem;
    }
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        margin-bottom: 12px;
    }
    .kpi-title {
        font-size: 0.82rem;
        font-weight: 700;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.85rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.15;
    }
    .kpi-sub {
        font-size: 0.85rem;
        color: #64748B;
        margin-top: 4px;
        font-weight: 500;
    }
    .alert-box-critical {
        background-color: #FEF2F2;
        border-left: 5px solid #EF4444;
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #991B1B;
    }
    .alert-box-soon {
        background-color: #FFFBEB;
        border-left: 5px solid #F59E0B;
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #92400E;
    }
    .alert-box-ok {
        background-color: #F0FDF4;
        border-left: 5px solid #10B981;
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #166534;
    }
</style>
""", unsafe_allow_html=True)


def format_inr(val: Optional[float], include_symbol: bool = True) -> str:
    """Formats numbers into Indian numbering format (Lakh / Crore with ₹)."""
    if val is None or pd.isna(val):
        return "₹ 0" if include_symbol else "0"
    v = float(val)
    sym = "₹ " if include_symbol else ""
    abs_v = abs(v)

    if abs_v >= 10000000:
        return f"{sym}{v / 10000000:.2f} Cr"
    elif abs_v >= 100000:
        return f"{sym}{v / 100000:.2f} Lakh"
    elif abs_v >= 1000:
        return f"{sym}{v:,.0f}"
    else:
        return f"{sym}{v:.1f}"


# =============================================================================
# 2. SESSION STATE & BILINGUAL DICTIONARY
# =============================================================================

if "service_level" not in st.session_state:
    st.session_state["service_level"] = 0.95

if "deadstock_threshold" not in st.session_state:
    st.session_state["deadstock_threshold"] = 90

if "language" not in st.session_state:
    st.session_state["language"] = "English"

if "forecast_horizon" not in st.session_state:
    st.session_state["forecast_horizon"] = 12

if "company_name" not in st.session_state:
    st.session_state["company_name"] = "Shree Durga Industrial Components Pvt. Ltd."

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "data_loaded" not in st.session_state:
    st.session_state["data_loaded"] = False
    st.session_state["sales_df"] = None
    st.session_state["purchases_df"] = None
    st.session_state["stock_df"] = None
    st.session_state["sales_report"] = None
    st.session_state["purchases_report"] = None
    st.session_state["stock_report"] = None

st.session_state.setdefault("data_updated_at", None)
st.session_state.setdefault("data_source", None)

LABELS = {
    "English": {
        "tagline": '"Aapka godam, ab smart."',
        "sub_tagline": "Demand & Inventory Forecasting for Manufacturing Factories",
        "nav_upload": "📁 1. Data Upload",
        "nav_overview": "📊 2. Factory Overview",
        "nav_forecast": "📈 3. Demand Forecast",
        "nav_alerts": "🚨 4. Reorder Alerts",
        "nav_deadstock": "🛑 5. Dead Stock",
        "nav_assistant": "💬 6. Ask Godam AI",
        "nav_report": "📄 7. PDF Health Report",
        "nav_settings": "⚙️ 8. Settings",
        "kpi_deadstock": "Cash Locked in Dead Stock",
        "kpi_stockout": "SKUs at Risk of Stockout",
        "kpi_accuracy": "Forecast Model Accuracy",
        "kpi_reorder": "Items to Reorder This Week",
        "no_data_msg": "No factory data loaded yet. Please open **1. Data Upload** to load sample files or upload your Excel ledgers.",
        "sample_btn": "Load 24-Month Factory Sample Data",
        "update_btn": "🔄 Update factory data",
    },
    "Hindi": {
        "tagline": '"आपका गोदाम, अब स्मार्ट।"',
        "sub_tagline": "छोटे विनिर्माण कारखानों के लिए मांग और स्टॉक प्रबंधन",
        "nav_upload": "📁 1. डेटा अपलोड (Upload)",
        "nav_overview": "📊 2. गोदाम स्थिति (Overview)",
        "nav_forecast": "📈 3. मांग अनुमान (Forecast)",
        "nav_alerts": "🚨 4. रीऑर्डर अलर्ट (Reorder Alerts)",
        "nav_deadstock": "🛑 5. डेड स्टॉक (Dead Stock)",
        "nav_assistant": "💬 6. गोदाम सहायक (Ask AI)",
        "nav_report": "📄 7. पीडीएफ रिपोर्ट (Health Report)",
        "nav_settings": "⚙️ 8. सेटिंग्स (Settings)",
        "kpi_deadstock": "डेड स्टॉक में फंसा पैसा",
        "kpi_stockout": "14 दिनों में खत्म होने वाले सामान",
        "kpi_accuracy": "औसत मांग अनुमान सटीकता",
        "kpi_reorder": "इस सप्ताह ऑर्डर करने वाले सामान",
        "no_data_msg": "अभी कोई डेटा लोड नहीं है। कृपया **1. डेटा अपलोड** में जाकर सैंपल डेटा लोड करें या अपनी एक्सेल फाइलें अपलोड करें।",
        "sample_btn": "24 महीने का सैंपल डेटा लोड करें",
        "update_btn": "🔄 फैक्ट्री डेटा अपडेट करें",
    },
}

lang = st.session_state["language"]
T = LABELS[lang]


# Helper function to auto-load sample data
def load_builtin_sample_data():
    base_dir = Path(__file__).resolve().parent
    sample_dir = base_dir / "sample_data"

    if not (sample_dir / "sales.csv").exists():
        from sample_data.generate import generate_sample_data
        generate_sample_data(str(sample_dir))

    sales_df, sales_rep = load_sales(sample_dir / "sales.csv")
    purch_df, purch_rep = load_purchases(sample_dir / "purchases.csv")
    stock_df, stock_rep = load_stock(sample_dir / "stock.csv")

    st.session_state["sales_df"] = sales_df
    st.session_state["sales_report"] = sales_rep
    st.session_state["purchases_df"] = purch_df
    st.session_state["purchases_report"] = purch_rep
    st.session_state["stock_df"] = stock_df
    st.session_state["stock_report"] = stock_rep
    st.session_state["data_loaded"] = True
    st.session_state["data_updated_at"] = datetime.now()
    st.session_state["data_source"] = "Sample data"


# Auto-load built-in sample data on first launch so the dashboard is immediately interactive
if not st.session_state["data_loaded"]:
    try:
        load_builtin_sample_data()
    except Exception:
        pass


# =============================================================================
# 3. SIDEBAR NAVIGATION
# =============================================================================

st.sidebar.markdown(f"## 🏭 Godam AI\n*{T['tagline']}*")

if st.sidebar.button(T["update_btn"], use_container_width=True):
    st.session_state["navigation"] = "upload"
    st.rerun()

navigation_pages = [
    "upload",
    "overview",
    "forecast",
    "alerts",
    "deadstock",
    "assistant",
    "report",
    "settings",
]
selected_page = st.sidebar.radio(
    "Navigation:",
    navigation_pages,
    format_func=lambda page_key: T[f"nav_{page_key}"],
    index=1 if st.session_state["data_loaded"] else 0,
    key="navigation",
)
page = T[f"nav_{selected_page}"]

st.sidebar.markdown("---")
if st.session_state["data_loaded"]:
    st.sidebar.success("✅ Factory Ledger Active")
    st.sidebar.caption(f"Sales: {len(st.session_state['sales_df']):,} rows | Stock: {len(st.session_state['stock_df'])} SKUs")
    if st.session_state["data_source"]:
        st.sidebar.caption(f"Source: {st.session_state['data_source']}")
    if st.session_state["data_updated_at"]:
        st.sidebar.caption(
            f"Last updated: {st.session_state['data_updated_at']:%d %b %Y, %I:%M %p}"
        )
else:
    st.sidebar.warning("⚠️ No Ledger Loaded")

st.sidebar.caption("Godam AI v1.0 • Built for Indian Manufacturing SMEs")


# Helper to run analytics with caching
@st.cache_data(show_spinner=False)
def run_analytics_cached(sales_df, purchases_df, stock_df, service_level, deadstock_days, horizon):
    # 1. Forecasting
    forecasts = forecast_all_products(sales_df, forecast_horizon=horizon, backtest_weeks=8)
    summary_table = get_forecast_summary_table(forecasts)

    # 2. Inventory Optimization
    inv_optimizer = InventoryOptimizer(service_level=service_level)
    inventory_df, alerts = inv_optimizer.optimize_all(
        stock_df=stock_df,
        purchases_df=purchases_df,
        product_forecasts=forecasts,
    )

    # 3. Deadstock
    deadstock_analyzer = DeadstockAnalyzer(inactivity_threshold_days=deadstock_days)
    deadstock_rep = deadstock_analyzer.analyze_inventory(
        stock_df=stock_df,
        sales_df=sales_df,
        purchases_df=purchases_df,
        inactivity_threshold_days=deadstock_days,
    )

    return forecasts, summary_table, inventory_df, alerts, deadstock_rep


# =============================================================================
# PAGE 1: UPLOAD & DATA QUALITY
# =============================================================================

if page == T["nav_upload"]:
    st.markdown('<div class="main-title">📁 Data Upload & Quality Cleaner</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Upload messy Excel or Tally/Vyapar CSV files. Godam AI automatically maps Hindi/English columns and cleans errors.</div>', unsafe_allow_html=True)

    if st.session_state["data_loaded"]:
        last_updated = st.session_state["data_updated_at"]
        updated_text = (
            f" Last updated {last_updated:%d %b %Y, %I:%M %p}."
            if last_updated
            else ""
        )
        st.info(
            f"Upload complete, up-to-date versions of all three ledgers to replace the current data.{updated_text} "
            "Your current data stays active unless all new files are processed successfully."
        )
    else:
        st.info("Upload your latest Sales, Purchases, and Stock files to get started.")

    col_sample, col_or = st.columns([2, 3])
    with col_sample:
        if st.button(f"⚡ {T['sample_btn']}", type="primary", use_container_width=True):
            with st.spinner("Loading 24-month realistic Indian manufacturing dataset..."):
                load_builtin_sample_data()
                st.success("✅ Sample factory data loaded successfully!")
                st.rerun()

    st.markdown("---")
    st.markdown("#### ⬆️ Upload Your Factory Files (Excel / CSV)")

    up_c1, up_c2, up_c3 = st.columns(3)
    with up_c1:
        f_sales = st.file_uploader("1. Sales Ledger", type=["csv", "xlsx", "xls"], help="Must contain date, product, quantity")
    with up_c2:
        f_purch = st.file_uploader("2. Purchases / Inward", type=["csv", "xlsx", "xls"], help="Must contain date, material, quantity, lead time")
    with up_c3:
        f_stock = st.file_uploader("3. Current Stock", type=["csv", "xlsx", "xls"], help="Must contain item, current stock, rate")

    if f_sales and f_purch and f_stock:
        process_label = (
            "🔄 Update Factory Data"
            if st.session_state["data_loaded"]
            else "🚀 Process & Clean Uploaded Files"
        )
        if st.button(process_label, use_container_width=True):
            try:
                with st.spinner("Cleaning messy columns, converting mixed dates, and removing duplicates..."):
                    s_df, s_rep = load_sales(f_sales)
                    p_df, p_rep = load_purchases(f_purch)
                    st_df, st_rep = load_stock(f_stock)

                    st.session_state["sales_df"] = s_df
                    st.session_state["sales_report"] = s_rep
                    st.session_state["purchases_df"] = p_df
                    st.session_state["purchases_report"] = p_rep
                    st.session_state["stock_df"] = st_df
                    st.session_state["stock_report"] = st_rep
                    st.session_state["data_loaded"] = True
                    st.session_state["data_updated_at"] = datetime.now()
                    st.session_state["data_source"] = "Uploaded ledgers"

                st.success("🎉 Factory data updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(
                    f"❌ Error processing files: {e}. Please ensure files are valid Excel or CSV. "
                    "Your previously loaded data has not been changed."
                )

    # Data Quality Report Card
    if st.session_state["data_loaded"]:
        st.markdown("---")
        st.markdown("### 📋 Data Quality Diagnostic Report")

        s_rep = st.session_state["sales_report"]
        p_rep = st.session_state["purchases_report"]

        r_c1, r_c2, r_c3, r_c4 = st.columns(4)
        health_score = s_rep.health_score if s_rep else 100.0

        with r_c1:
            st.metric("Overall Data Health", f"{health_score:.1f}%", help="Higher score indicates clean columns, complete dates, and zero corruption")
        with r_c2:
            st.metric("Clean Sales Records", f"{len(st.session_state['sales_df']):,}")
        with r_c3:
            st.metric("Purchases Inward", f"{len(st.session_state['purchases_df']):,}")
        with r_c4:
            st.metric("SKUs in Godam", f"{len(st.session_state['stock_df'])}")

        with st.expander("🛠️ View Auto-Fixes Applied by Cleaner", expanded=True):
            if s_rep and s_rep.fixes_applied:
                for fix in s_rep.fixes_applied[:6]:
                    st.markdown(f"- ✅ **Sales Ledger**: {fix}")
            if p_rep and p_rep.fixes_applied:
                for fix in p_rep.fixes_applied[:4]:
                    st.markdown(f"- ✅ **Purchases Ledger**: {fix}")
            if s_rep and s_rep.warnings:
                for w in s_rep.warnings:
                    st.markdown(f"- ⚠️ **Warning**: {w}")


# =============================================================================
# PAGE 2: FACTORY OVERVIEW
# =============================================================================

elif page == T["nav_overview"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    forecasts, summary_table, inventory_df, alerts, deadstock_rep = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">📊 Factory Overview & Health Snapshot</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-tagline">Real-time working capital, stockout risks, and demand trajectory for factory leadership.</div>', unsafe_allow_html=True)

    # 4 Top KPI Cards
    crit_count = sum(1 for a in alerts if a.urgency == "Critical")
    soon_count = sum(1 for a in alerts if a.urgency == "Soon")
    reorder_this_week = crit_count + soon_count

    stockout_14d_count = sum(
        1 for _, row in inventory_df.iterrows()
        if float(row.get("days_of_supply", 999)) <= 14.0
    )

    avg_accuracy = np.mean([res.accuracy_pct for res in forecasts.values()]) if forecasts else 85.0
    locked_cash_str = format_inr(deadstock_rep.total_cash_locked_rupees)

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 5px solid #EF4444;">
            <div class="kpi-title">{T["kpi_deadstock"]}</div>
            <div class="kpi-value" style="color:#DC2626;">{locked_cash_str}</div>
            <div class="kpi-sub">{deadstock_rep.deadstock_items_count} idle items ({deadstock_rep.deadstock_share_percentage:.1f}% of godam)</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi2:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 5px solid #F59E0B;">
            <div class="kpi-title">{T["kpi_stockout"]}</div>
            <div class="kpi-value" style="color:#D97706;">{stockout_14d_count} SKUs</div>
            <div class="kpi-sub">Critical production buffer warning</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi3:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 5px solid #2563EB;">
            <div class="kpi-title">{T["kpi_accuracy"]}</div>
            <div class="kpi-value" style="color:#1D4ED8;">{avg_accuracy:.1f}%</div>
            <div class="kpi-sub">8-week tournament backtested</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi4:
        st.markdown(f"""
        <div class="kpi-card" style="border-left: 5px solid #10B981;">
            <div class="kpi-title">{T["kpi_reorder"]}</div>
            <div class="kpi-value" style="color:#059669;">{reorder_this_week} Materials</div>
            <div class="kpi-sub">{crit_count} Critical orders + {soon_count} Soon</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Top Action Recommendations Today
    st.markdown("### ⚡ Action Items for Factory Management Today")

    col_act1, col_act2 = st.columns(2)

    with col_act1:
        st.markdown("##### 🚨 Urgent Procurement POs Needed")
        urgent_alerts = [a for a in alerts if a.urgency in ("Critical", "Soon")]
        if urgent_alerts:
            for alert in urgent_alerts[:3]:
                badge = "🚨 CRITICAL" if alert.urgency == "Critical" else "⚠️ SOON"
                st.markdown(f"""
                <div class="{ 'alert-box-critical' if alert.urgency=='Critical' else 'alert-box-soon' }">
                    <b>{badge}:</b> {alert.alert_message}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ All raw materials have healthy buffers. No urgent purchase orders required today.")

    with col_act2:
        st.markdown("##### 🛑 Top Dead Stock Liquidation Priorities")
        if deadstock_rep.ranked_deadstock_items:
            for item in deadstock_rep.ranked_deadstock_items[:3]:
                st.markdown(f"""
                <div class="kpi-card">
                    <div style="font-weight:700;font-size:1.05rem;color:#0F172A;">{item.item_name} ({item.item_id})</div>
                    <div style="color:#DC2626;font-weight:700;font-size:1.15rem;margin:4px 0;">{format_inr(item.cash_locked_rupees)} locked <span style="font-size:0.85rem;color:#64748B;">({item.days_inactive} days idle)</span></div>
                    <div style="font-size:0.85rem;color:#334155;">💡 <b>Action:</b> {item.recommendation}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("🎉 No dead stock items detected! Godam turnover is optimal.")


# =============================================================================
# PAGE 3: DEMAND FORECAST
# =============================================================================

elif page == T["nav_forecast"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    forecasts, summary_table, _, _, _ = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">📈 Demand Forecasting & Model Selection</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Automatically compares Moving Average, Exponential Smoothing, Croston SBA, and Prophet on an 8-week backtest to pick the winning model.</div>', unsafe_allow_html=True)

    product_pids = list(forecasts.keys())
    sel_pid = st.selectbox(
        "Select Finished Product to Inspect:",
        options=product_pids,
        format_func=lambda pid: f"{pid} — {forecasts[pid].product_name}",
    )

    sel_res = forecasts[sel_pid]

    f_c1, f_c2, f_c3, f_c4 = st.columns(4)
    with f_c1:
        st.metric("Tournament Winner", sel_res.best_model)
    with f_c2:
        st.metric("Backtest Accuracy", f"{sel_res.accuracy_pct:.1f}%", help="Based on 1.0 - WAPE over last 8 weeks")
    with f_c3:
        st.metric("Confidence Rating", sel_res.confidence.upper())
    with f_c4:
        tot_12w = sel_res.forecast_df["forecast"].sum()
        st.metric("Total 12-Week Demand", f"{tot_12w:,.0f} units")

    # Plotly Visualizer
    hw_df = sel_res.historical_weekly_df
    fc_df = sel_res.forecast_df

    fig = go.Figure()

    # History line
    fig.add_trace(go.Scatter(
        x=hw_df["week_date"], y=hw_df["quantity"],
        mode="lines+markers", name="Weekly Actual Sales",
        line=dict(color="#2563EB", width=2.5),
        marker=dict(size=4),
    ))

    # Upper bound
    fig.add_trace(go.Scatter(
        x=fc_df["week_date"], y=fc_df["upper_bound"],
        mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))

    # Lower bound with shaded confidence area
    fig.add_trace(go.Scatter(
        x=fc_df["week_date"], y=fc_df["lower_bound"],
        mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(249, 115, 22, 0.22)", name="80% Prediction Band (Lower/Upper)",
    ))

    # Forecast point line
    fig.add_trace(go.Scatter(
        x=fc_df["week_date"], y=fc_df["forecast"],
        mode="lines+markers", name=f"12W Forecast ({sel_res.best_model})",
        line=dict(color="#EA580C", width=3.5, dash="solid"),
        marker=dict(size=7, symbol="diamond"),
    ))

    # Mark Indian Festival Spikes (Diwali & Holi)
    for dt in hw_df["week_date"]:
        if dt.month in (10, 11) and dt.day <= 15:
            fig.add_vline(x=dt, line_dash="dot", line_color="#D97706", opacity=0.40)
        elif dt.month == 3 and dt.day <= 20:
            fig.add_vline(x=dt, line_dash="dot", line_color="#10B981", opacity=0.35)

    fig.update_layout(
        title=f"Weekly Demand Trajectory: {sel_res.product_name} ({sel_pid})",
        xaxis_title="Calendar Week", yaxis_title="Quantity (Units)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=50, b=40),
        height=480,
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tournament Scorecard
    with st.expander(f"🏆 Model Tournament Scorecard for {sel_pid}", expanded=False):
        score_rows = []
        for m_name, wape_v in sel_res.backtest_scores.items():
            is_winner = m_name == sel_res.best_model
            score_rows.append({
                "Algorithm": f"⭐ {m_name}" if is_winner else m_name,
                "Backtest WAPE Error": f"{wape_v:.4f}",
                "Accuracy Score": f"{(1.0 - wape_v) * 100:.1f}%",
                "Tournament Outcome": "SELECTED WINNER" if is_winner else "Evaluated",
            })
        st.table(pd.DataFrame(score_rows))

    st.markdown("---")
    st.markdown("#### 📋 Full Catalog Forecast Summary")
    st.dataframe(summary_table, use_container_width=True, hide_index=True)


# =============================================================================
# PAGE 4: REORDER ALERTS & EXCEL EXPORT
# =============================================================================

elif page == T["nav_alerts"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    _, _, inventory_df, alerts, _ = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">🚨 Raw Material Reorder Alerts & Purchase List</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Safety Stock & Reorder Points (ROP) calculated from supplier lead times and consumption forecasts.</div>', unsafe_allow_html=True)

    # Excel Download Button for Factory Purchase Manager
    col_dl1, col_dl2 = st.columns([3, 1])
    with col_dl2:
        try:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                inventory_df.to_excel(writer, index=False, sheet_name="Purchase_Schedule")
            dl_data = excel_buffer.getvalue()
            dl_filename = f"godam_purchase_orders_{datetime.now().strftime('%Y%m%d')}.xlsx"
            dl_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except Exception:
            dl_data = inventory_df.to_csv(index=False).encode("utf-8-sig")
            dl_filename = f"godam_purchase_orders_{datetime.now().strftime('%Y%m%d')}.csv"
            dl_mime = "text/csv"

        st.download_button(
            label="📥 Download Purchase List (Excel)",
            data=dl_data,
            file_name=dl_filename,
            mime=dl_mime,
            type="primary",
            use_container_width=True,
        )

    # Filter alerts by urgency
    urgency_filter = st.radio(
        "Filter Urgency:",
        ["All Alerts", "🚨 Critical Only", "⚠️ Soon Only", "✅ OK Only"],
        horizontal=True,
    )

    filtered_alerts = alerts
    if urgency_filter.startswith("🚨"):
        filtered_alerts = [a for a in alerts if a.urgency == "Critical"]
    elif urgency_filter.startswith("⚠️"):
        filtered_alerts = [a for a in alerts if a.urgency == "Soon"]
    elif urgency_filter.startswith("✅"):
        filtered_alerts = [a for a in alerts if a.urgency == "OK"]

    st.markdown("<br>", unsafe_allow_html=True)

    for alert in filtered_alerts:
        if alert.urgency == "Critical":
            st.markdown(f'<div class="alert-box-critical">🚨 <b>CRITICAL:</b> {alert.alert_message}</div>', unsafe_allow_html=True)
        elif alert.urgency == "Soon":
            st.markdown(f'<div class="alert-box-soon">⚠️ <b>SOON:</b> {alert.alert_message}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="alert-box-ok">✅ <b>OK:</b> {alert.alert_message}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 📋 Raw Materials ROP & Safety Stock Matrix")
    st.dataframe(inventory_df, use_container_width=True, hide_index=True)


# =============================================================================
# PAGE 5: DEAD STOCK & CAPITAL LOCKUP
# =============================================================================

elif page == T["nav_deadstock"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    _, _, _, _, deadstock_rep = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">🛑 Dead Stock & Locked Working Capital (₹)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-tagline">Items with zero movement for {st.session_state["deadstock_threshold"]}+ days. Liquidation priority ranked by frozen capital.</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">Total Godam Stock Value</div><div class="kpi-value">{format_inr(deadstock_rep.total_inventory_value_rupees)}</div><div class="kpi-sub">Total inventory asset</div></div>""", unsafe_allow_html=True)
    with m2:
        st.markdown(f"""<div class="kpi-card" style="border-left: 5px solid #EF4444;"><div class="kpi-title" style="color:#DC2626;">Cash Locked in Dead Stock</div><div class="kpi-value" style="color:#DC2626;">{format_inr(deadstock_rep.total_cash_locked_rupees)}</div><div class="kpi-sub">{deadstock_rep.deadstock_items_count} non-moving items</div></div>""", unsafe_allow_html=True)
    with m3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">Dead Stock Share %</div><div class="kpi-value">{deadstock_rep.deadstock_share_percentage:.1f}%</div><div class="kpi-sub">Target: &lt; 8.0%</div></div>""", unsafe_allow_html=True)
    with m4:
        st.markdown(f"""<div class="kpi-card" style="border-left: 5px solid #B45309;"><div class="kpi-title" style="color:#B45309;">Carrying Cost Loss / Year</div><div class="kpi-value" style="color:#B45309;">{format_inr(deadstock_rep.annual_carrying_loss_rupees)}/yr</div><div class="kpi-sub">Interest + godown rent loss</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Aging Bar Chart & Breakdown
    chart_c1, chart_c2 = st.columns([3, 2])

    with chart_c1:
        st.markdown("#### ⏳ Aging Distribution Breakdown")
        st.dataframe(deadstock_rep.aging_summary_df, use_container_width=True, hide_index=True)

    with chart_c2:
        st.markdown("#### 📊 Cash Locked by Aging Bucket")
        if not deadstock_rep.aging_summary_df.empty:
            bar_fig = go.Figure(go.Bar(
                x=deadstock_rep.aging_summary_df["Aging Bracket"],
                y=deadstock_rep.aging_summary_df["Value Locked (₹)"],
                marker_color=["#10B981", "#F59E0B", "#F97316", "#EF4444"],
                text=[format_inr(v) for v in deadstock_rep.aging_summary_df["Value Locked (₹)"]],
                textposition="auto",
            ))
            bar_fig.update_layout(
                yaxis_title="Rupees (₹)",
                margin=dict(l=20, r=20, t=20, b=20),
                height=280,
                template="plotly_white",
            )
            st.plotly_chart(bar_fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🏆 Liquidation Priority Table (Ranked by Locked Cash)")

    ds_rows = [item.to_dict() for item in deadstock_rep.ranked_deadstock_items]
    if ds_rows:
        st.dataframe(pd.DataFrame(ds_rows), use_container_width=True, hide_index=True)
    else:
        st.success(f"🎉 No dead stock detected! All items have moved within the last {st.session_state['deadstock_threshold']} days.")


# =============================================================================
# PAGE 6: ASK GODAM AI (ANTHROPIC CLAUDE NATURAL LANGUAGE ASSISTANT)
# =============================================================================

elif page == T["nav_assistant"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    forecasts, summary_table, inventory_df, alerts, deadstock_rep = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">💬 Ask Godam AI (गोदाम सहायक)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Ask any question in English, Hindi, or Hinglish. Godam AI answers strictly from your computed factory numbers.</div>', unsafe_allow_html=True)

    # Build privacy-safe computed context (NO raw transaction rows)
    assistant_context = build_assistant_context(
        forecast_results=forecasts,
        inventory_alerts=alerts,
        deadstock_report=deadstock_rep,
        company_name=st.session_state["company_name"],
    )

    assistant = GodamAssistant()

    # Quick Suggestion Prompts
    st.markdown("##### 💡 Suggested Questions / अक्सर पूछे जाने वाले सवाल:")
    p_c1, p_c2, p_c3, p_c4 = st.columns(4)

    preset_query = None
    if p_c1.button("🛒 Is hafte kya order karna hai?", use_container_width=True):
        preset_query = "Is hafte kya order karna hai?"
    if p_c2.button("🛑 Kaun sa maal paisa phasa raha hai?", use_container_width=True):
        preset_query = "Kaun sa maal paisa phasa raha hai?"
    if p_c3.button("⚠️ Stockout ka kya risk hai?", use_container_width=True):
        preset_query = "Agle 14 din me stockout ka kya risk hai?"
    if p_c4.button("📈 Agle mahine ki demand kitni hai?", use_container_width=True):
        preset_query = "Agle mahine ki demand kitni hai?"

    st.markdown("---")

    # Display Chat History
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # User Input
    user_prompt = st.chat_input("Poochiye: e.g. Is hafte kya order karna hai? / Which items are in dead stock?")
    active_prompt = preset_query or user_prompt

    if active_prompt:
        st.session_state["chat_history"].append({"role": "user", "content": active_prompt})
        with st.chat_message("user"):
            st.markdown(active_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Godam AI is analyzing factory metrics..."):
                reply = assistant.ask(active_prompt, assistant_context)
                st.markdown(reply)
                st.session_state["chat_history"].append({"role": "assistant", "content": reply})


# =============================================================================
# PAGE 7: EXECUTIVE 1-PAGE PDF REPORT (SALES TOOL)
# =============================================================================

elif page == T["nav_report"]:
    if not st.session_state["data_loaded"]:
        st.info(T["no_data_msg"])
        st.stop()

    forecasts, summary_table, inventory_df, alerts, deadstock_rep = run_analytics_cached(
        st.session_state["sales_df"],
        st.session_state["purchases_df"],
        st.session_state["stock_df"],
        st.session_state["service_level"],
        st.session_state["deadstock_threshold"],
        st.session_state["forecast_horizon"],
    )

    st.markdown('<div class="main-title">📄 One-Page Executive Godam Health Report</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Crisp, professional 1-page PDF designed as a high-impact sales tool for first meetings with factory owners (Seth ji).</div>', unsafe_allow_html=True)

    rep_col1, rep_col2 = st.columns([2, 1])

    with rep_col1:
        comp_name_input = st.text_input(
            "Company / Factory Name for Report:",
            value=st.session_state["company_name"],
            help="This will appear prominently in the header of the official audit report",
        )
        if comp_name_input != st.session_state["company_name"]:
            st.session_state["company_name"] = comp_name_input

    with rep_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if FPDF_AVAILABLE:
            try:
                pdf_bytes = ReportGenerator.generate_health_report_pdf(
                    deadstock_report=deadstock_rep,
                    inventory_alerts=alerts,
                    company_name=st.session_state["company_name"],
                    audit_date=datetime.now(),
                )
                filename = f"Godam_Health_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                st.download_button(
                    label="📥 Download 1-Page PDF Report",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"❌ Could not generate PDF: {e}")
        else:
            st.warning("⚠️ `fpdf2` is required for PDF download. Run: `pip install fpdf2`")

    st.markdown("---")
    st.markdown("#### 👁️ PDF Report Executive Preview")

    # Visual preview of what will be in the PDF
    p_box1, p_box2, p_box3 = st.columns(3)
    with p_box1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">Total Godam Inventory Value</div><div class="kpi-value">{format_inr(deadstock_rep.total_inventory_value_rupees)}</div></div>""", unsafe_allow_html=True)
    with p_box2:
        st.markdown(f"""<div class="kpi-card" style="border-left: 5px solid #EF4444;"><div class="kpi-title" style="color:#DC2626;">Cash Locked in Dead Stock</div><div class="kpi-value" style="color:#DC2626;">{format_inr(deadstock_rep.total_cash_locked_rupees)}</div><div class="kpi-sub">{deadstock_rep.deadstock_share_percentage:.1f}% of total inventory</div></div>""", unsafe_allow_html=True)
    with p_box3:
        st.markdown(f"""<div class="kpi-card" style="border-left: 5px solid #F59E0B;"><div class="kpi-title" style="color:#B45309;">Annual Holding Drain (~20%/yr)</div><div class="kpi-value" style="color:#B45309;">{format_inr(deadstock_rep.annual_carrying_loss_rupees)}/yr</div></div>""", unsafe_allow_html=True)

    st.markdown("##### 💡 3 Key Executive Sales Recommendations in Report:")
    st.markdown(f"""
    1. **Immediate Working Capital Release**: Liquidate top dead stock items (e.g. solder wire, legacy bases) to recover **{format_inr(deadstock_rep.total_cash_locked_rupees * 0.70)}** in operating cash.
    2. **Zero Production Stoppage**: Submit purchase orders for critical copper and brass materials before deadlines to avoid factory machine idle time.
    3. **Automated Procurement Discipline**: Replace static monthly Excel ledgers with Godam AI automated ROP discipline to permanently halt future deadstock accumulation.
    """)


# =============================================================================
# PAGE 8: SETTINGS & PREFERENCES
# =============================================================================

elif page == T["nav_settings"]:
    st.markdown('<div class="main-title">⚙️ Factory Settings & Preferences</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-tagline">Configure safety buffers, dead stock criteria, and language preferences.</div>', unsafe_allow_html=True)

    set_col1, set_col2 = st.columns(2)

    with set_col1:
        st.markdown("##### 🌐 Language / भाषा")
        selected_lang = st.radio(
            "Dashboard Display Language:",
            ["English", "Hindi"],
            index=0 if st.session_state["language"] == "English" else 1,
            format_func=lambda x: "English (US/UK)" if x == "English" else "हिंदी (Hindi - 'Aapka godam, ab smart')",
        )
        if selected_lang != st.session_state["language"]:
            st.session_state["language"] = selected_lang
            st.rerun()

        st.markdown("---")
        st.markdown("##### 🛡️ Service Level (Stockout Protection)")
        sl_choice = st.select_slider(
            "Target Service Level:",
            options=[0.85, 0.90, 0.95, 0.98, 0.99],
            value=st.session_state["service_level"],
            format_func=lambda x: f"{int(x * 100)}% (Z = {1.645 if x==0.95 else (1.282 if x==0.90 else (2.054 if x==0.98 else (2.326 if x==0.99 else 1.036)))})",
            help="Higher service level guarantees fewer stockouts, but requires higher safety stock.",
        )
        st.session_state["service_level"] = sl_choice
        st.caption("💡 *Factory Default is 95%: 19 out of 20 times you will never run out of raw materials before a shipment arrives.*")

    with set_col2:
        st.markdown("##### 🛑 Dead Stock Inactivity Threshold")
        ds_days = st.slider(
            "Inactivity Period (Days):",
            min_value=60,
            max_value=180,
            value=st.session_state["deadstock_threshold"],
            step=15,
            help="Items with no sales or procurement for this many days will be flagged as dead stock.",
        )
        st.session_state["deadstock_threshold"] = ds_days

        st.markdown("---")
        st.markdown("##### 📅 Forward Forecast Horizon")
        fc_horizon = st.slider(
            "Forecast Window (Weeks):",
            min_value=4,
            max_value=24,
            value=st.session_state["forecast_horizon"],
            step=2,
            help="Number of future weeks to project demand.",
        )
        st.session_state["forecast_horizon"] = fc_horizon

    st.markdown("---")
    if st.button("💾 Apply & Save Settings", type="primary"):
        st.success("✅ Settings updated successfully!")
        st.rerun()


# =============================================================================
# FOOTER
# =============================================================================

st.markdown("<br><hr>", unsafe_allow_html=True)
st.caption("🏭 Godam AI • Aapka godam, ab smart • Designed for Small Manufacturing Factories in India")
