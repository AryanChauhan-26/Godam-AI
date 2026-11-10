# 🏭 Godam AI (गोदाम एआई)
> *"Aapka godam, ab smart."*

**Godam AI** is an intelligent demand forecasting and inventory optimization platform built specifically for small manufacturing factories (SMEs) in India that currently run on Excel registers, Tally, Vyapar, or Busy ledgers.

Unlike generic enterprise software (SAP/Oracle), Godam AI is designed for factory owners (Seth ji) and plant heads: it embraces messy Hindi/English spreadsheets, handles festival surges (**Diwali, Holi**), identifies dead stock locking up working capital in **₹ Lakhs**, and alerts managers before raw material stockouts halt factory production.

---

## 🚀 Key Capabilities

1. **Robust SME Data Layer & Cleaner (`modules/data_loader.py`)**:
   - Ingests messy Excel (`.xlsx`, `.xls`) and CSV files.
   - Fuzzy column detection matching English, Hindi (Devanagari: `मात्रा`, `दिनांक`, `सामग्री`, `इकाई`), and Hinglish aliases.
   - Cleans text inside number columns (`"150 pcs"`, `"₹ 4,500"`, `"25 kg"`, `"(50)"` accounting negatives).
   - Resolves both `DD/MM/YYYY` (Indian standard) and `MM/DD/YYYY`, plus Excel numeric serial dates.
   - Computes a 0–100% **Data Quality Health Score** and logs all auto-fixes.

2. **8-Week Tournament Demand Forecasting (`modules/forecasting.py`)**:
   - Aggregates daily sales to continuous Monday-anchored weeks (`W-MON`) with automatic zero-filling.
   - Evaluates 4 candidate models: **Moving Average**, **Exponential Smoothing (Holt-Winters)**, **Croston's Method with Syntetos-Boylan Approximation (SBA)**, and **Prophet**.
   - Backtests on the last 8 weeks and automatically selects the algorithm with the lowest **WAPE** (Weighted Absolute Percentage Error).
   - Generates 12-week projections with $80\%$ confidence bands (clipped at 0).
   - Cold-start guard: Products with $< 12$ weeks of data default to Moving Average flagged as *"low confidence"*.

3. **Inventory Reorder & Urgency Alerts (`modules/inventory.py`)**:
   - Accounts for both demand variability ($\sigma_D$) and supplier lead-time variability ($\sigma_L$).
   - Calculates **Safety Stock (SS)** at configurable service levels (default 95%, $Z = 1.645$).
   - Computes **Reorder Point (ROP)** and **Economic Order Quantity (EOQ)** / Weeks-of-Cover.
   - Color-coded urgency alerts:
     - 🚨 **Critical**: *"Order 455 kg of Electrolytic Copper Strip by Thursday, 05 Nov or stock runs out on 15 Nov."*
     - ⚠️ **Soon**: Order within 7 days to avoid dipping into safety buffer.
     - ✅ **OK**: Healthy inventory buffer.
   - 1-Click Excel purchase order export.

4. **Dead Stock & Working Capital Recovery (`modules/deadstock.py`)**:
   - Flags items idle for 90+ days.
   - Calculates frozen capital in Indian Rupees ($\text{Current Qty} \times \text{Unit Cost}$) in **₹ Lakhs / Crores**.
   - Quantifies the annual holding drain ($\approx 20\%/\text{year}$ in bank CC limit interest, space, and deterioration).
   - Categorizes stock into aging brackets (`Active`, `At Risk`, `Slow Moving`, `Deadstock`).
   - Generates actionable SME recovery plans (vendor buybacks, scrap/melt recovery, discount bundling).

5. **"Ask Godam AI" Natural Language Assistant (`modules/assistant.py`)**:
   - Conversational assistant powered by **Anthropic Claude**.
   - Accepts prompts in **English, Hindi, or Hinglish**:
     - *"Is hafte kya order karna hai?"*
     - *"Kaun sa maal paisa phasa raha hai?"*
   - **Strict Privacy & Safety Guardrail**: Sends ONLY computed summary metrics (never raw data), answers only from the numbers, and strictly replies *"Mere paas yeh data nahi hai"* for unrecorded queries.

6. **Executive 1-Page PDF "Godam Health Report" (`modules/report.py`)**:
   - Built with `fpdf2` strictly formatted for a **single A4 page**.
   - Includes company header, financial snapshot, top 5 stockout risks, top 5 dead stock items, and 3 plain-language recommendations.
   - High-impact sales tool for introductory meetings with factory owners.

---

## 🛠️ Tech Stack

- **Python**: 3.11 (supports 3.9 through 3.12+)
- **Data Processing**: `pandas`, `numpy`, `openpyxl`
- **Forecasting**: `statsmodels`, `prophet`
- **UI & Visualization**: `streamlit`, `plotly`
- **PDF Generation**: `fpdf2`
- **AI Assistant**: `anthropic`
- **Testing**: `pytest`, `unittest`

---

## 📂 Project Architecture

```text
Godam AI/
├── app.py                     # Streamlit application with 8 pages
├── requirements.txt           # Production dependencies
├── README.md                  # Documentation and deployment guide
├── modules/
│   ├── __init__.py            # Module exports
│   ├── data_loader.py         # Fuzzy column mapping, cleaner & quality reporter
│   ├── forecasting.py         # 8-week backtest tournament & 12W projections
│   ├── inventory.py           # Safety Stock, ROP, EOQ, and reorder alerts
│   ├── deadstock.py           # 90+ day inactivity & working capital analysis
│   ├── assistant.py           # Anthropic Claude natural language assistant
│   └── report.py              # 1-page executive PDF health report (fpdf2)
├── sample_data/
│   ├── generate.py            # 24-month realistic Indian manufacturing data generator
│   ├── sales.csv              # 2,967 rows of daily sales with Diwali/Holi spikes
│   ├── purchases.csv          # 602 rows of material procurement transactions
│   └── stock.csv              # 16 SKUs with dead stock candidates
└── tests/
    ├── __init__.py
    ├── test_core_math.py      # Zero-dependency standard library verification
    ├── test_data_loader.py    # Ingestion & cleaner tests
    ├── test_forecasting.py    # Forecasting tournament & WAPE tests
    ├── test_inventory.py      # Inventory formulas & alerts tests
    └── test_assistant_and_report.py  # Assistant guardrails & PDF tests
```

---

## 💻 Local Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/godam-ai.git
cd "godam-ai"
```

### 2. Create and Activate a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate       # On macOS/Linux
# .venv\Scripts\activate       # On Windows
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional for Assistant)
To enable the AI conversational assistant, export your Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```
*(If omitted, Godam AI automatically runs its built-in deterministic contextual answering engine).*

### 5. Run the Test Suite
Verify that all algorithms and cleaners pass:
```bash
# Instant zero-dependency tests
python3 -m unittest tests/test_core_math.py -v

# Full integration test suite
pytest -v tests/
```

### 6. Launch the Godam AI Web App
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## ☁️ Streamlit Community Cloud Deployment Guide

Deploy Godam AI to the web for free in under 3 minutes:

### Step 1: Push Code to GitHub
Ensure all files are committed to your GitHub repository:
```bash
git add .
git commit -m "feat: complete Godam AI MVP application"
git push origin main
```

### Step 2: Sign In to Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and log in with your GitHub account.
2. Click the **"New app"** button.

### Step 3: Configure Deployment
- **Repository**: Select your `godam-ai` repository.
- **Branch**: `main`
- **Main file path**: `app.py`
- **App URL**: Choose a custom subdomain (e.g. `godam-ai.streamlit.app`).

### Step 4: Configure Secrets (Anthropic API Key)
1. In the deployment setup dialog, click **"Advanced settings..."**.
2. Under **Secrets**, paste your API key in TOML format:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-..."
   ```
3. Click **"Save"**.

### Step 5: Click "Deploy!"
Streamlit Community Cloud will automatically build your virtual environment using `requirements.txt` and launch the live web application. Share the link with factory owners and clients!

---

## 📄 License
Built with ❤️ for Indian Manufacturing SMEs. Licensed under the MIT License.

