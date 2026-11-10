"""Godam AI - Robust Data Loader & Cleaner for Manufacturing SMEs
"Aapka godam, ab smart."

Handles real-world messy SME Excel and CSV files:
- Formats: CSV (auto-detects delimiter & encoding) and Excel (.xlsx, .xls)
- Column mapping: Fuzzy matching for English, Hindi (Devanagari), and Hinglish
- Data cleaning: Text inside number columns ("100 pcs", "₹ 4,500", "20 kg", "(50)")
- Date parsing: DD/MM/YYYY (India standard), MM/DD/YYYY, ISO, and Excel date serials
- Deduplication: Removes duplicate rows and completely blank records
- Quality reporting: Generates DataQualityReport with fixes, dropped rows, and health score
"""

from __future__ import annotations

import csv
import difflib
import io
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

import math

try:
    import numpy as np
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    np = None
    pd = None
    PANDAS_AVAILABLE = False


# =============================================================================
# DATA QUALITY REPORT
# =============================================================================

@dataclass
class DataQualityReport:
    """Detailed diagnostic report of data loading and cleaning operations."""
    dataset_type: str
    initial_rows: int = 0
    final_rows: int = 0
    initial_cols: int = 0
    final_cols: int = 0
    mapped_columns: Dict[str, str] = field(default_factory=dict)  # raw_col -> canonical_col
    unmapped_columns: List[str] = field(default_factory=list)
    missing_required_columns: List[str] = field(default_factory=list)
    rows_dropped: int = 0
    drop_reasons: Dict[str, int] = field(default_factory=dict)
    fixes_applied: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    health_score: float = 100.0  # Percentage (0 - 100%)

    def compute_health_score(self) -> float:
        """Computes a 0-100 data health score reflecting dataset reliability."""
        if self.initial_rows == 0:
            self.health_score = 0.0
            return 0.0

        score = 100.0

        # Penalize for missing required columns (heavy penalty)
        if self.missing_required_columns:
            score -= min(50.0, len(self.missing_required_columns) * 20.0)

        # Penalize for percentage of rows dropped
        drop_ratio = self.rows_dropped / max(1, self.initial_rows)
        score -= min(30.0, drop_ratio * 50.0)

        # Penalize for unmapped columns (mild penalty)
        if self.unmapped_columns:
            score -= min(10.0, len(self.unmapped_columns) * 2.0)

        # Penalize for warnings
        if self.warnings:
            score -= min(15.0, len(self.warnings) * 3.0)

        self.health_score = max(0.0, round(score, 1))
        return self.health_score

    def to_dict(self) -> Dict[str, Any]:
        """Converts report to dictionary representation."""
        return {
            "dataset_type": self.dataset_type,
            "health_score": self.health_score,
            "initial_rows": self.initial_rows,
            "final_rows": self.final_rows,
            "rows_dropped": self.rows_dropped,
            "drop_reasons": self.drop_reasons,
            "initial_cols": self.initial_cols,
            "final_cols": self.final_cols,
            "mapped_columns": self.mapped_columns,
            "unmapped_columns": self.unmapped_columns,
            "missing_required_columns": self.missing_required_columns,
            "fixes_applied": self.fixes_applied,
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        """Returns human-readable text summary for factory dashboard display."""
        status = "Healthy" if self.health_score >= 85 else ("Acceptable" if self.health_score >= 65 else "Attention Needed")
        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Godam AI Data Quality Report: {self.dataset_type.upper()}",
            f"  Health Score: {self.health_score}% ({status})",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"• Records: {self.final_rows} valid (started with {self.initial_rows}, dropped {self.rows_dropped})",
            f"• Columns Mapped: {len(self.mapped_columns)} of {self.initial_cols}",
        ]

        if self.mapped_columns:
            mappings_str = ", ".join(f"'{k}' ➔ '{v}'" for k, v in list(self.mapped_columns.items())[:5])
            if len(self.mapped_columns) > 5:
                mappings_str += f" (+{len(self.mapped_columns) - 5} more)"
            lines.append(f"  Mapped: {mappings_str}")

        if self.missing_required_columns:
            lines.append(f"  Missing Required: {', '.join(self.missing_required_columns)}")

        if self.unmapped_columns:
            lines.append(f"  Unmapped Extra Columns: {', '.join(self.unmapped_columns)}")

        if self.drop_reasons:
            reasons_str = ", ".join(f"{reason}: {count}" for reason, count in self.drop_reasons.items())
            lines.append(f"• Drops: {reasons_str}")

        if self.fixes_applied:
            lines.append(f"• Auto-Fixes Applied ({len(self.fixes_applied)}):")
            for fix in self.fixes_applied[:4]:
                lines.append(f"   ✓ {fix}")
            if len(self.fixes_applied) > 4:
                lines.append(f"   ... and {len(self.fixes_applied) - 4} more fixes")

        if self.warnings:
            lines.append(f"• Warnings ({len(self.warnings)}):")
            for warn in self.warnings[:3]:
                lines.append(f"   ⚠️  {warn}")

        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


# =============================================================================
# CANONICAL SCHEMAS & SYNONYM DICTIONARIES
# =============================================================================

CANONICAL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "sales": {
        "required": ["date", "product_id", "quantity"],
        "all": ["date", "product_id", "product_name", "quantity", "customer"],
        "types": {
            "date": "datetime64[ns]",
            "product_id": "string",
            "product_name": "string",
            "quantity": "float64",
            "customer": "string",
        },
    },
    "purchases": {
        "required": ["date", "material_id", "quantity"],
        "all": ["date", "material_id", "material_name", "quantity", "supplier", "lead_time_days"],
        "types": {
            "date": "datetime64[ns]",
            "material_id": "string",
            "material_name": "string",
            "quantity": "float64",
            "supplier": "string",
            "lead_time_days": "float64",
        },
    },
    "stock": {
        "required": ["item_id", "current_qty"],
        "all": ["item_id", "item_name", "type", "current_qty", "unit", "last_movement_date", "unit_cost"],
        "types": {
            "item_id": "string",
            "item_name": "string",
            "type": "string",
            "current_qty": "float64",
            "unit": "string",
            "last_movement_date": "datetime64[ns]",
            "unit_cost": "float64",
        },
    },
}

# Column aliases including Hindi / Devanagari and Hinglish variants
COLUMN_ALIASES: Dict[str, List[str]] = {
    # Quantities
    "quantity": [
        "quantity", "qty", "qty.", "qnty", "qnt", "units", "pcs", "nos", "volume",
        "sales qty", "order qty", "purchase qty", "billed qty", "dispatch qty",
        "मात्रा", "संख्या", "इकाइयां", "तादाद", "matra", "bikri matra",
    ],
    "current_qty": [
        "current_qty", "current qty", "curr qty", "closing qty", "stock qty",
        "in stock", "available stock", "on hand", "closing balance", "balance qty",
        "current stock", "stock in hand", "inventory", "baki stock", "godown stock",
        "मौजूदा स्टॉक", "स्टॉक मात्रा", "वर्तमान मात्रा", "बैलेंस",
    ],
    # Dates
    "date": [
        "date", "bill date", "invoice date", "order date", "txn date", "txndate",
        "sales date", "purchase date", "posting date", "entry date", "voucher date",
        "दिनांक", "तारीख", "tarikh", "tariq", "dinank", "bill dinank",
    ],
    "last_movement_date": [
        "last_movement_date", "last movement date", "last sale date", "last dispatch date",
        "last issue date", "last active date", "movement date", "last transaction date",
        "अंतिम हलचल", "पिछली तारीख", "last movement",
    ],
    # Product / Item IDs
    "product_id": [
        "product_id", "product id", "prod id", "product code", "item code",
        "sku", "part no", "part number", "item_id", "item id", "model no",
        "उत्पाद कोड", "कोड", "part #", "sku code",
    ],
    "material_id": [
        "material_id", "material id", "raw material id", "material code", "rm code",
        "item code", "sku", "part no", "सामग्री कोड", "कच्चा माल कोड",
    ],
    "item_id": [
        "item_id", "item id", "item code", "product_id", "material_id", "sku",
        "part no", "part number", "code", "आइटम कोड", "सामान कोड",
    ],
    # Names & Descriptions
    "product_name": [
        "product_name", "product name", "item name", "description", "product description",
        "item description", "particulars", "name", "उत्पाद नाम", "विवरण", "नाम", "सामान",
    ],
    "material_name": [
        "material_name", "material name", "material description", "raw material",
        "particulars", "description", "item name", "सामग्री नाम", "कच्चा माल",
    ],
    "item_name": [
        "item_name", "item name", "product name", "material name", "item description",
        "description", "particulars", "सामान का नाम", "वस्तु नाम",
    ],
    # Parties
    "customer": [
        "customer", "customer name", "client", "party", "party name", "buyer",
        "account name", "consignee", "ग्राहक", "पार्टी नाम", "खरीदार",
    ],
    "supplier": [
        "supplier", "supplier name", "vendor", "vendor name", "party", "party name",
        "seller", "creditor", "आपूर्तिकर्ता", "व्यापारी", "विक्रेता",
    ],
    # Operations
    "lead_time_days": [
        "lead_time_days", "lead time days", "lead time", "lead_time", "delivery days",
        "tat", "turnaround time", "dispatch days", "लीड टाइम", "दिन", "delivery period",
    ],
    "type": [
        "type", "item type", "category", "material type", "raw/finished", "rm/fg",
        "classification", "प्रकार", "कच्चा या तैयार",
    ],
    "unit": [
        "unit", "uom", "unit of measure", "measure", "unit of measurement",
        "measuring unit", "इकाई", "माप इकाई",
    ],
    "unit_cost": [
        "unit_cost", "unit cost", "cost price", "rate", "unit rate", "price",
        "purchase rate", "purchase price", "cost per unit", "laagat", "दर", "लागत", "कीमत",
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _normalize_string(text: str) -> str:
    """Strips accents, punctuation, and extra whitespace for fuzzy matching."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    # Lowercase, replace underscores/hyphens/slashes with space
    cleaned = re.sub(r"[_\-/\\]+", " ", text.lower())
    # Remove brackets, quotes, punctuation
    cleaned = re.sub(r"[()\[\]{}#.,:;?!\'\"]+", "", cleaned)
    # Collapse multiple whitespaces
    return " ".join(cleaned.split())


def _clean_numeric_cell(val: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Cleans messy strings in numeric cells.
    Handles: "100 pcs", "₹ 4,500.50", "20 kg", "(50)", "approx 50", "1,200", etc.
    Returns: (cleaned_float_value, fix_description_if_applied)
    """
    if val is None:
        return None, None
    if pd is not None and pd.isna(val):
        return None, None
    if isinstance(val, float) and math.isnan(val):
        return None, None

    if np is not None:
        if isinstance(val, (int, float, np.integer, np.floating)):
            return float(val), None
    elif isinstance(val, (int, float)):
        return float(val), None

    val_str = str(val).strip()
    if not val_str:
        return None, None

    # Check for known null words
    if val_str.lower() in ("nan", "none", "null", "n/a", "na", "-", "--", "nil", "unknown", "?"):
        return None, f"Coerced '{val_str}' to null"

    original_str = val_str

    # Handle accounting negative format: (50) -> -50
    is_accounting_negative = False
    if val_str.startswith("(") and val_str.endswith(")"):
        is_accounting_negative = True
        val_str = val_str[1:-1].strip()

    # Remove currency symbols (₹, $, Rs, Rs., INR, etc.)
    val_str = re.sub(r"(?i)[₹$€£]|(?:rs\.?|inr)\s*", "", val_str)

    # Remove text units (pcs, kg, mtr, ltr, nos, bags, boxes, units, days, etc.)
    val_str = re.sub(r"(?i)\s*(?:pcs|pc|kg|kgs|mtr|meter|meters|ltr|litre|litres|nos|no|boxes|box|bags|bag|units|unit|days|day|hrs|hr|hours)\b", "", val_str)

    # Remove approximate prefixes (~, approx, abt)
    val_str = re.sub(r"(?i)^[~≈\s]*(?:approx\.?|abt\.?)?\s*", "", val_str)

    # Remove thousands comma separators: 1,234.56 -> 1234.56
    val_str = val_str.replace(",", "")

    # Clean any remaining stray text, leaving digits, decimal point, and leading minus
    match = re.search(r"[-+]?\d*\.?\d+", val_str)
    if match:
        try:
            num = float(match.group())
            if is_accounting_negative and num > 0:
                num = -num
            fix = f"Cleaned text in number: '{original_str}' ➔ {num}" if original_str != str(num) else None
            return num, fix
        except ValueError:
            pass

    return None, f"Could not parse numeric value from '{original_str}', coerced to null"


def _parse_dates_robust(series: pd.Series, prefer_dayfirst: bool = True) -> Tuple[pd.Series, int, int]:
    """
    Robust date parser supporting:
    - DD/MM/YYYY (Indian standard)
    - MM/DD/YYYY
    - YYYY-MM-DD (ISO)
    - Mixed formats and Excel numeric serial dates (e.g. 45220)
    Returns: (parsed_series, success_count, fail_count)
    """
    cleaned_series = series.copy()

    # Step 1: Detect and convert Excel numeric serial dates (e.g. 44560 -> 2022-01-01)
    def handle_excel_serial(val: Any) -> Any:
        if pd.isna(val) or val is None or val == "":
            return np.nan
        # If already a datetime or timestamp
        if isinstance(val, (pd.Timestamp, datetime)):
            return val
        if isinstance(val, (int, float, np.integer, np.floating)):
            # Excel dates are usually between 30000 (1982) and 60000 (2064)
            if 30000 <= val <= 60000:
                base_date = datetime(1899, 12, 30)
                return base_date + timedelta(days=float(val))
        val_str = str(val).strip()
        if val_str.isdigit():
            num = int(val_str)
            if 30000 <= num <= 60000:
                return datetime(1899, 12, 30) + timedelta(days=num)
        return val_str

    cleaned_series = cleaned_series.apply(handle_excel_serial)

    # Step 2: Try fast vector parsing with dayfirst
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(cleaned_series, dayfirst=prefer_dayfirst, errors="coerce")

        # Step 3: For rows that resulted in NaT, try parsing with dayfirst=False or explicit patterns
        unparsed_mask = parsed.isna() & cleaned_series.notna() & (cleaned_series != "")
        if unparsed_mask.any():
            fallback_parsed = pd.to_datetime(cleaned_series[unparsed_mask], dayfirst=not prefer_dayfirst, errors="coerce")
            valid_fallback = fallback_parsed.dropna()
            if not valid_fallback.empty:
                parsed.loc[valid_fallback.index] = valid_fallback

    # Step 4: For any stubborn dates remaining, try common Indian date regex formats
    still_unparsed = parsed.isna() & cleaned_series.notna() & (cleaned_series != "")
    if still_unparsed.any():
        for idx in cleaned_series.index[still_unparsed]:
            raw_val = str(cleaned_series.loc[idx]).strip()
            # Try matching DD-MM-YYYY, DD/MM/YYYY, etc.
            match = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", raw_val)
            if match:
                d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if y < 100:
                    y += 2000
                try:
                    # Prefer DD/MM/YYYY if plausible
                    if prefer_dayfirst and 1 <= d <= 31 and 1 <= m <= 12:
                        parsed.loc[idx] = pd.Timestamp(year=y, month=m, day=d)
                    elif not prefer_dayfirst and 1 <= d <= 12 and 1 <= m <= 31:
                        parsed.loc[idx] = pd.Timestamp(year=y, month=d, day=m)
                    elif 1 <= m <= 12 and 1 <= d <= 31:
                        parsed.loc[idx] = pd.Timestamp(year=y, month=m, day=d)
                except Exception:
                    pass

    success_count = int(parsed.notna().sum())
    fail_count = int((cleaned_series.notna() & (cleaned_series != "") & parsed.isna()).sum())
    return parsed, success_count, fail_count


# =============================================================================
# DATA LOADER CLASS
# =============================================================================

class DataLoader:
    """Production-grade data loader and cleaner for SME manufacturing datasets."""

    def __init__(self, fuzzy_threshold: float = 0.70):
        self.fuzzy_threshold = fuzzy_threshold

    def read_raw_data(self, file_source: Union[str, Path, bytes, BinaryIO]) -> pd.DataFrame:
        """
        Reads raw CSV or Excel into a pandas DataFrame.
        Auto-detects delimiters (comma, semicolon, tab) and encodings.
        """
        if not PANDAS_AVAILABLE or pd is None:
            raise RuntimeError("pandas is required. Please run: pip install -r requirements.txt")
        # 1. Handle file paths
        if isinstance(file_source, (str, Path)):
            path_obj = Path(file_source)
            if not path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_source}")

            suffix = path_obj.suffix.lower()
            if suffix in (".xlsx", ".xls", ".xlsm"):
                return pd.read_excel(file_source, engine="openpyxl" if suffix != ".xls" else None)
            else:
                return self._read_csv_with_fallback(file_source)

        # 2. Handle bytes
        if isinstance(file_source, bytes):
            buffer = io.BytesIO(file_source)
            # Try reading as excel first if signature matches
            if file_source.startswith(b"PK\x03\x04") or file_source.startswith(b"\xd0\xcf\x11\xe0"):
                try:
                    return pd.read_excel(buffer)
                except Exception:
                    buffer.seek(0)
            return self._read_csv_buffer(buffer)

        # 3. Handle file-like objects (e.g. Streamlit UploadedFile, io.BytesIO, io.StringIO)
        if hasattr(file_source, "read"):
            if hasattr(file_source, "seek"):
                try:
                    file_source.seek(0)
                except Exception:
                    pass

            # Inspect name if available
            name = getattr(file_source, "name", "").lower()
            if name.endswith((".xlsx", ".xls", ".xlsm")):
                return pd.read_excel(file_source)

            # For BytesIO or general file object
            content = file_source.read()
            if isinstance(content, str):
                return self._read_csv_buffer(io.StringIO(content))
            else:
                if content.startswith(b"PK\x03\x04") or content.startswith(b"\xd0\xcf\x11\xe0"):
                    try:
                        return pd.read_excel(io.BytesIO(content))
                    except Exception:
                        pass
                return self._read_csv_buffer(io.BytesIO(content))

        raise ValueError(f"Unsupported file source type: {type(file_source)}")

    def _read_csv_with_fallback(self, file_path: Union[str, Path]) -> pd.DataFrame:
        """Reads CSV trying standard encodings and auto-sniffing delimiters."""
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        delimiters = [None, ",", ";", "\t", "|"]

        last_error = None
        for enc in encodings:
            for sep in delimiters:
                try:
                    df = pd.read_csv(
                        file_path,
                        encoding=enc,
                        sep=sep,
                        engine="python" if sep is None else "c",
                        on_bad_lines="skip",
                    )
                    if len(df.columns) > 1 or len(delimiters) == 1:
                        return df
                except Exception as e:
                    last_error = e

        # Final attempt
        try:
            return pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip")
        except Exception:
            raise ValueError(f"Failed to read CSV file {file_path}: {last_error}")

    def _read_csv_buffer(self, buffer: Union[io.BytesIO, io.StringIO]) -> pd.DataFrame:
        """Reads CSV from in-memory buffer."""
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        if isinstance(buffer, io.BytesIO):
            raw_bytes = buffer.getvalue()
            for enc in encodings:
                try:
                    text = raw_bytes.decode(enc)
                    return pd.read_csv(io.StringIO(text), sep=None, engine="python", on_bad_lines="skip")
                except Exception:
                    continue
            return pd.read_csv(io.BytesIO(raw_bytes), on_bad_lines="skip")
        else:
            return pd.read_csv(buffer, sep=None, engine="python", on_bad_lines="skip")

    def detect_dataset_type(self, raw_columns: List[str]) -> str:
        """
        Auto-detects whether the dataset is 'sales', 'purchases', or 'stock'.
        Uses column name matching scores.
        """
        norm_cols = [_normalize_string(c) for c in raw_columns]

        scores = {"sales": 0, "purchases": 0, "stock": 0}

        for norm in norm_cols:
            # Check sales indicators
            if any(term in norm for term in ["sale", "customer", "client", "buyer", "party", "bikri"]):
                scores["sales"] += 3
            if any(term in norm for term in ["product", "sku"]):
                scores["sales"] += 1

            # Check purchases indicators
            if any(term in norm for term in ["purchase", "supplier", "vendor", "lead time", "tat", "kharid"]):
                scores["purchases"] += 3
            if any(term in norm for term in ["material", "raw"]):
                scores["purchases"] += 2

            # Check stock indicators
            if any(term in norm for term in ["stock", "closing", "current qty", "in hand", "balance", "godam", "godown"]):
                scores["stock"] += 3
            if any(term in norm for term in ["unit cost", "cost price", "rate", "movement"]):
                scores["stock"] += 2

        best_type = max(scores, key=scores.get)
        # Default to 'sales' if ambiguous
        return best_type if scores[best_type] > 0 else "sales"

    def map_columns(
        self,
        raw_columns: List[str],
        dataset_type: str,
    ) -> Tuple[Dict[str, str], List[str], List[str]]:
        """
        Fuzzy matches raw columns against target canonical schema.
        Returns: (column_mapping, unmapped_columns, missing_required_columns)
        """
        schema = CANONICAL_SCHEMAS.get(dataset_type, CANONICAL_SCHEMAS["sales"])
        target_cols = schema["all"]
        required_cols = schema["required"]

        mapping: Dict[str, str] = {}
        matched_targets: Set[str] = set()

        # Priority 1: Exact matches against target column names
        for raw in raw_columns:
            norm_raw = _normalize_string(raw)
            for target in target_cols:
                if target in matched_targets:
                    continue
                if norm_raw == _normalize_string(target):
                    mapping[raw] = target
                    matched_targets.add(target)
                    break

        # Priority 2: Match against known aliases dictionary (exact or substring)
        for raw in raw_columns:
            if raw in mapping:
                continue
            norm_raw = _normalize_string(raw)
            best_target = None
            best_score = 0.0

            for target in target_cols:
                if target in matched_targets:
                    continue
                aliases = COLUMN_ALIASES.get(target, [])
                for alias in aliases:
                    norm_alias = _normalize_string(alias)
                    # Exact alias match
                    if norm_raw == norm_alias:
                        best_target = target
                        best_score = 1.0
                        break
                    # Word boundary or substring containment
                    if norm_alias in norm_raw or norm_raw in norm_alias:
                        score = len(norm_alias) / max(len(norm_raw), len(norm_alias))
                        if score > best_score:
                            best_score = score
                            best_target = target

                if best_score == 1.0:
                    break

            if best_target and best_score >= 0.5:
                mapping[raw] = best_target
                matched_targets.add(best_target)

        # Priority 3: Fuzzy difflib sequence matching
        for raw in raw_columns:
            if raw in mapping:
                continue
            norm_raw = _normalize_string(raw)
            best_target = None
            highest_ratio = 0.0

            for target in target_cols:
                if target in matched_targets:
                    continue
                # Compare against target name and aliases
                candidates = [target] + COLUMN_ALIASES.get(target, [])
                for cand in candidates:
                    norm_cand = _normalize_string(cand)
                    ratio = difflib.SequenceMatcher(None, norm_raw, norm_cand).ratio()
                    if ratio > highest_ratio:
                        highest_ratio = ratio
                        best_target = target

            if best_target and highest_ratio >= self.fuzzy_threshold:
                mapping[raw] = best_target
                matched_targets.add(best_target)

        # Special fallback: item_id vs product_id vs material_id cross-compatibility
        if "product_id" in required_cols and "product_id" not in matched_targets:
            for raw, mapped in list(mapping.items()):
                if mapped in ("item_id", "material_id"):
                    mapping[raw] = "product_id"
                    matched_targets.add("product_id")
                    break

        if "material_id" in required_cols and "material_id" not in matched_targets:
            for raw, mapped in list(mapping.items()):
                if mapped in ("item_id", "product_id"):
                    mapping[raw] = "material_id"
                    matched_targets.add("material_id")
                    break

        if "item_id" in required_cols and "item_id" not in matched_targets:
            for raw, mapped in list(mapping.items()):
                if mapped in ("product_id", "material_id"):
                    mapping[raw] = "item_id"
                    matched_targets.add("item_id")
                    break

        unmapped = [c for c in raw_columns if c not in mapping]
        missing_required = [c for c in required_cols if c not in matched_targets]

        return mapping, unmapped, missing_required

    def load_and_clean(
        self,
        file_source: Union[str, Path, bytes, BinaryIO],
        dataset_type: str = "auto",
        prefer_dayfirst: bool = True,
        drop_duplicates: bool = True,
        drop_invalid_dates: bool = True,
    ) -> Tuple[pd.DataFrame, DataQualityReport]:
        """
        Main pipeline: Reads, maps, cleans, validates, and reports on data quality.
        """
        raw_df = self.read_raw_data(file_source)
        initial_rows = len(raw_df)
        initial_cols = len(raw_df.columns)

        # Auto-detect dataset type if requested
        if dataset_type == "auto":
            dataset_type = self.detect_dataset_type([str(c) for c in raw_df.columns])

        report = DataQualityReport(
            dataset_type=dataset_type,
            initial_rows=initial_rows,
            initial_cols=initial_cols,
        )

        # Step 1: Drop completely empty rows and columns
        df = raw_df.dropna(how="all").copy()
        rows_empty_dropped = initial_rows - len(df)
        if rows_empty_dropped > 0:
            report.rows_dropped += rows_empty_dropped
            report.drop_reasons["Completely blank rows"] = rows_empty_dropped
            report.fixes_applied.append(f"Dropped {rows_empty_dropped} completely empty rows")

        # Step 2: Auto-detect and map columns
        raw_cols_list = [str(c) for c in df.columns]
        mapping, unmapped, missing_required = self.map_columns(raw_cols_list, dataset_type)
        report.mapped_columns = mapping
        report.unmapped_columns = unmapped
        report.missing_required_columns = missing_required

        # Rename mapped columns
        df = df.rename(columns=mapping)

        # Record column mapping fixes
        for raw_c, canonical_c in mapping.items():
            if raw_c != canonical_c:
                report.fixes_applied.append(f"Mapped column '{raw_c.strip()}' ➔ '{canonical_c}'")

        if missing_required:
            report.warnings.append(
                f"Missing critical required column(s): {', '.join(missing_required)}. "
                "Downstream forecasting or inventory calculations may fail."
            )

        if unmapped:
            report.warnings.append(f"Retained {len(unmapped)} unmapped column(s): {', '.join(unmapped)}")

        # Step 3: Deduplication
        if drop_duplicates:
            dup_mask = df.duplicated()
            dup_count = int(dup_mask.sum())
            if dup_count > 0:
                df = df[~dup_mask].copy()
                report.rows_dropped += dup_count
                report.drop_reasons["Duplicate rows"] = (
                    report.drop_reasons.get("Duplicate rows", 0) + dup_count
                )
                report.fixes_applied.append(f"Removed {dup_count} duplicate rows")

        # Step 4: String trimming across all text columns
        for col in df.columns:
            if df[col].dtype == object:
                # Strip leading/trailing whitespaces if strings
                sample_is_str = df[col].dropna().apply(lambda x: isinstance(x, str))
                if sample_is_str.any():
                    df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # Step 5: Clean Numeric Columns (quantity, current_qty, lead_time_days, unit_cost)
        numeric_targets = ["quantity", "current_qty", "lead_time_days", "unit_cost"]
        for num_col in numeric_targets:
            if num_col in df.columns:
                cleaned_vals = []
                fix_count = 0
                sample_fixes = []

                for val in df[num_col]:
                    cleaned, fix_desc = _clean_numeric_cell(val)
                    cleaned_vals.append(cleaned)
                    if fix_desc:
                        fix_count += 1
                        if len(sample_fixes) < 2:
                            sample_fixes.append(fix_desc)

                df[num_col] = pd.to_numeric(cleaned_vals, errors="coerce")

                if fix_count > 0:
                    report.fixes_applied.append(
                        f"Cleaned {fix_count} values in '{num_col}' (e.g., {sample_fixes[0]})"
                    )

                # Check for suspicious negative quantities
                neg_count = int((df[num_col] < 0).sum())
                if neg_count > 0:
                    report.warnings.append(
                        f"Found {neg_count} negative value(s) in '{num_col}'. "
                        "Please verify returns/adjustments."
                    )

        # Step 6: Parse Dates (date, last_movement_date)
        date_targets = ["date", "last_movement_date"]
        for dt_col in date_targets:
            if dt_col in df.columns:
                parsed_dates, success_cnt, fail_cnt = _parse_dates_robust(
                    df[dt_col], prefer_dayfirst=prefer_dayfirst
                )
                df[dt_col] = parsed_dates
                if success_cnt > 0:
                    report.fixes_applied.append(
                        f"Parsed {success_cnt} dates in '{dt_col}' using DD/MM/YYYY auto-detection"
                    )

                if drop_invalid_dates and dt_col == "date":
                    # Drop rows with missing or unparseable dates in sales/purchases
                    invalid_mask = df[dt_col].isna()
                    drop_cnt = int(invalid_mask.sum())
                    if drop_cnt > 0:
                        df = df[~invalid_mask].copy()
                        report.rows_dropped += drop_cnt
                        report.drop_reasons[f"Invalid or missing {dt_col}"] = (
                            report.drop_reasons.get(f"Invalid or missing {dt_col}", 0) + drop_cnt
                        )
                        report.fixes_applied.append(f"Dropped {drop_cnt} rows with missing or unparseable '{dt_col}'")
                elif fail_cnt > 0:
                    report.warnings.append(
                        f"Found {fail_cnt} unparseable or blank date(s) in '{dt_col}'"
                    )

        # Step 7: Drop rows with missing crucial identifier if specified
        id_col = next((c for c in ["product_id", "material_id", "item_id"] if c in df.columns), None)
        if id_col:
            missing_ids = df[id_col].isna() | (df[id_col] == "")
            missing_id_cnt = int(missing_ids.sum())
            if missing_id_cnt > 0:
                df = df[~missing_ids].copy()
                report.rows_dropped += missing_id_cnt
                report.drop_reasons[f"Missing {id_col}"] = (
                    report.drop_reasons.get(f"Missing {id_col}", 0) + missing_id_cnt
                )
                report.fixes_applied.append(f"Dropped {missing_id_cnt} rows missing '{id_col}'")

        # Step 8: Standardize Data Types
        schema_types = CANONICAL_SCHEMAS.get(dataset_type, {}).get("types", {})
        for col_name, dtype in schema_types.items():
            if col_name in df.columns:
                try:
                    if dtype.startswith("datetime"):
                        df[col_name] = pd.to_datetime(df[col_name])
                    elif dtype == "float64":
                        df[col_name] = df[col_name].astype(float)
                    elif dtype == "string":
                        df[col_name] = df[col_name].fillna("").astype(str)
                except Exception:
                    pass

        # Finalize report metrics
        report.final_rows = len(df)
        report.final_cols = len(df.columns)
        report.compute_health_score()

        return df.reset_index(drop=True), report


# =============================================================================
# CONVENIENCE MODULE FUNCTIONS
# =============================================================================

_DEFAULT_LOADER = DataLoader()


def load_and_clean_data(
    file_source: Union[str, Path, bytes, BinaryIO],
    dataset_type: str = "auto",
    prefer_dayfirst: bool = True,
    drop_duplicates: bool = True,
    drop_invalid_dates: bool = True,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """Convenience function for DataLoader.load_and_clean."""
    return _DEFAULT_LOADER.load_and_clean(
        file_source=file_source,
        dataset_type=dataset_type,
        prefer_dayfirst=prefer_dayfirst,
        drop_duplicates=drop_duplicates,
        drop_invalid_dates=drop_invalid_dates,
    )


def load_sales(
    file_source: Union[str, Path, bytes, BinaryIO],
    prefer_dayfirst: bool = True,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """Loads and cleans sales dataset."""
    return _DEFAULT_LOADER.load_and_clean(
        file_source=file_source,
        dataset_type="sales",
        prefer_dayfirst=prefer_dayfirst,
    )


def load_purchases(
    file_source: Union[str, Path, bytes, BinaryIO],
    prefer_dayfirst: bool = True,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """Loads and cleans purchases dataset."""
    return _DEFAULT_LOADER.load_and_clean(
        file_source=file_source,
        dataset_type="purchases",
        prefer_dayfirst=prefer_dayfirst,
    )


def load_stock(
    file_source: Union[str, Path, bytes, BinaryIO],
    prefer_dayfirst: bool = True,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """Loads and cleans inventory stock dataset."""
    return _DEFAULT_LOADER.load_and_clean(
        file_source=file_source,
        dataset_type="stock",
        prefer_dayfirst=prefer_dayfirst,
        drop_invalid_dates=False,  # stock movement dates may be optional
    )

