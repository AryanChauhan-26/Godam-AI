# Godam-AI

Godam AI is a smart inventory and demand forecasting tool for small factories. Upload your Excel sales and stock data to get accurate demand forecasts, timely reorder alerts, and a clear view of dead stock, so you never run out of materials and stop locking cash in unsold inventory.

---

## The Problem

Small factories often plan with gut feeling and Excel. This leads to two costly mistakes at the same time:

- **Overstock:** cash gets locked in raw material and finished goods that sit for months.
- **Stockouts:** a missing material stops production or loses a customer order.

## The Solution

Godam AI reads a factory's own sales, purchase, and stock files and tells the owner **what to order, how much, and when**. No new hardware and no complex software installation.

## Features

- **Excel/CSV upload** with automatic column detection and data cleaning
now - **Data updates** by uploading the latest sales, purchase, and stock ledgers; the dashboard records the last successful update
- **Demand forecasting** per product for the next 12 weeks, with confidence ranges
- **Automatic model selection** (moving average, exponential smoothing, Prophet, Croston for slow movers) based on backtesting
- **Reorder alerts** with safety stock, reorder point, and recommended order quantity
- **Dead stock report** showing how much cash is locked in slow or unmoving items
- **Simple dashboard** built for factory owners, with Indian number formatting (lakh/crore, ₹)
- **Ask Godam AI:** a chat assistant that answers questions from your computed results
- **Free PDF health report** to share with factory owners

## Tech Stack

| Area | Tools |
|---|---|
| Language | Python 3.11 |
| Data | pandas, numpy, openpyxl |
| Forecasting | statsmodels, Prophet |
| Dashboard | Streamlit, Plotly |
| Reports | fpdf2 |
| AI assistant | Anthropic API |

## Project Structure

```
Godam-AI/
├── app.py                  # Streamlit dashboard
├── modules/
│   ├── data_loader.py      # Upload, cleaning, column mapping
│   ├── forecasting.py      # Demand forecasting engine
│   ├── inventory.py        # Safety stock, reorder points, alerts
│   ├── deadstock.py        # Dead and slow-moving stock analysis
│   ├── report.py           # PDF health report
│   └── assistant.py        # AI chat assistant
├── sample_data/
│   └── generate.py         # Sample data generator
├── tests/
├── requirements.txt
└── README.md
```



## Input Data Format

Godam AI accepts Excel (.xlsx) or CSV files. Column names are matched automatically, so they don't need to be exact.


| File | Expected columns |
|---|---|
| **Sales** | date, product, quantity, customer |
| **Purchases** | date, material, quantity, supplier, lead time (days) |
| **Stock** | item, type (raw/finished), current quantity, unit, last movement date, unit cost |

## How It Works

1. **Clean:** the uploaded data is checked, fixed, and summarized in a data-quality report.
2. **Forecast:** weekly demand is predicted per product, and the best model is chosen by backtesting on recent weeks.
3. **Plan inventory:** safety stock, reorder points, and order quantities are calculated for each material.
4. **Alert:** items are ranked as Critical, Soon, or OK, with clear instructions on what to order and by when.
5. **Free cash:** dead and slow-moving stock is listed with the rupee value locked in it.

## Updating Data

Use **Update factory data** in the Streamlit sidebar to open the upload page. Upload complete, up-to-date Sales, Purchases, and Stock files, then select **Update Factory Data**. All three files are cleaned before replacing the current datasets; if processing fails, the previously loaded data remains active. The sidebar shows the time of the last successful update. Updates are held in the current Streamlit session, so upload the files again in a new session.

## Privacy

Only computed summaries (forecasts, alerts, dead stock totals) are sent to the AI assistant. Raw factory data stays on your machine or server.

## Author

Built by <Aryan Chauhan>. Connect on [LinkedIn](www.linkedin.com/in/aryanchauhan7).
