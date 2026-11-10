"""Godam AI - Intelligent Natural Language Assistant
"Aapka godam, ab smart."

Key Capabilities:
1. Contextual Natural Language Answering via Anthropic API (Claude):
   - Accepts user queries in English, Hindi, or Hinglish (Roman Hindi):
     e.g. "Is hafte kya order karna hai?", "Kaun sa maal paisa phasa raha hai?", "Which item has highest demand?"
   - Sends ONLY computed metrics, forecasts, alerts, and deadstock summaries as context (NEVER raw data).
   - Strict Guardrails: Answers ONLY from the given numbers and says "Mere paas yeh data nahi hai" otherwise.
2. Built-in Deterministic Fallback:
   - If ANTHROPIC_API_KEY is not configured or network is offline, provides an intelligent
     contextual rule-based response matching the user's question, preserving zero-crash behavior.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Union

# Attempt import of anthropic SDK
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False


# =============================================================================
# CONTEXT BUILDER (COMPUTED NUMBERS ONLY, NO RAW DATA)
# =============================================================================

def build_assistant_context(
    forecast_results: Optional[Dict[str, Any]] = None,
    inventory_alerts: Optional[List[Any]] = None,
    deadstock_report: Optional[Any] = None,
    company_name: str = "Shree Durga Industrial Components Pvt. Ltd.",
) -> Dict[str, Any]:
    """
    Builds a compact, privacy-safe summary of computed factory metrics.
    Strictly excludes raw transaction rows.
    """
    context: Dict[str, Any] = {
        "company_name": company_name,
        "summary_metrics": {},
        "urgent_reorders": [],
        "healthy_materials": [],
        "top_deadstock_items": [],
        "top_forecast_items": [],
    }

    # 1. Deadstock Context
    if deadstock_report is not None:
        context["summary_metrics"]["total_inventory_value_rupees"] = getattr(deadstock_report, "total_inventory_value_rupees", 0.0)
        context["summary_metrics"]["total_cash_locked_in_deadstock_rupees"] = getattr(deadstock_report, "total_cash_locked_rupees", 0.0)
        context["summary_metrics"]["deadstock_share_percentage"] = getattr(deadstock_report, "deadstock_share_percentage", 0.0)
        context["summary_metrics"]["annual_carrying_cost_drain_rupees"] = getattr(deadstock_report, "annual_carrying_loss_rupees", 0.0)

        ranked = getattr(deadstock_report, "ranked_deadstock_items", [])
        for item in ranked[:6]:
            context["top_deadstock_items"].append({
                "item_id": getattr(item, "item_id", ""),
                "item_name": getattr(item, "item_name", ""),
                "type": getattr(item, "item_type", ""),
                "current_qty": getattr(item, "current_qty", 0.0),
                "unit": getattr(item, "unit", ""),
                "cash_locked_rupees": getattr(item, "cash_locked_rupees", 0.0),
                "days_inactive": getattr(item, "days_inactive", 0),
                "aging_bracket": getattr(item, "aging_bracket", ""),
                "recommended_action": getattr(item, "recommendation", ""),
            })

    # 2. Inventory Alerts Context
    if inventory_alerts:
        for a in inventory_alerts:
            entry = {
                "material_id": getattr(a, "material_id", ""),
                "material_name": getattr(a, "material_name", ""),
                "urgency": getattr(a, "urgency", ""),
                "recommended_qty": getattr(a, "recommended_qty", 0.0),
                "unit": getattr(a, "unit", ""),
                "current_stock": getattr(a, "current_stock", 0.0),
                "reorder_point": getattr(a, "reorder_point", 0.0),
                "deadline": a.order_deadline.strftime("%A, %d %b %Y") if getattr(a, "order_deadline", None) else "Immediate",
                "stockout_date": a.stockout_date.strftime("%d %b %Y") if getattr(a, "stockout_date", None) else "Unknown",
                "alert_message": getattr(a, "alert_message", ""),
            }
            if getattr(a, "urgency", "") in ("Critical", "Soon"):
                context["urgent_reorders"].append(entry)
            else:
                context["healthy_materials"].append(entry)

    # 3. Forecasts Context
    if forecast_results:
        for pid, res in list(forecast_results.items())[:8]:
            tot_fc = float(res.forecast_df["forecast"].sum()) if hasattr(res, "forecast_df") else 0.0
            avg_w = float(res.forecast_df["forecast"].mean()) if hasattr(res, "forecast_df") else 0.0
            context["top_forecast_items"].append({
                "product_id": pid,
                "product_name": getattr(res, "product_name", pid),
                "best_model": getattr(res, "best_model", ""),
                "accuracy_pct": getattr(res, "accuracy_pct", 0.0),
                "confidence": getattr(res, "confidence", ""),
                "total_12w_demand": round(tot_fc, 1),
                "avg_weekly_demand": round(avg_w, 1),
            })

    return context


# =============================================================================
# GODAM ASSISTANT CLASS
# =============================================================================

class GodamAssistant:
    """Natural language conversational assistant for Indian factory management."""

    SYSTEM_PROMPT = """You are Godam AI, an expert manufacturing godam (warehouse & inventory) assistant for small manufacturing factories in India. Tagline: "Aapka godam, ab smart."

Users are factory owners, plant heads, and purchase managers. They will ask questions in English, Hindi, or Hinglish (e.g. "Is hafte kya order karna hai?", "Kaun sa maal paisa phasa raha hai?").

STRICT OPERATING RULES:
1. Answer ONLY using the exact numbers and metrics provided in the COMPUTED FACTORY CONTEXT below.
2. If the user asks about something NOT provided in the numbers or context, strictly reply:
   "Mere paas yeh data nahi hai." (or in English: "I do not have this data in the current ledger records.")
3. Do NOT invent, assume, or extrapolate any numbers not explicitly in the context.
4. Keep answers concise, direct, polite, and actionable for a busy factory owner (Seth ji).
5. Always quote monetary values in Indian Rupees (₹) with Lakhs or Crores where appropriate (e.g., ₹ 3.33 Lakh).
6. Match the language of the user's prompt (Hindi, Hinglish, or English).
"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.model = model
        self.client = None

        if self.api_key and ANTHROPIC_AVAILABLE:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception:
                self.client = None

    def ask(self, query: str, context: Union[Dict[str, Any], str]) -> str:
        """
        Processes user query using Claude (via Anthropic API) with guardrails,
        or falls back to deterministic context matching if API is not active.
        """
        if not query or not query.strip():
            return "Kripya apna sawal poochein (Please ask a question about your inventory, orders, or dead stock)."

        # Format context into string if dict
        if isinstance(context, dict):
            context_str = json.dumps(context, indent=2, ensure_ascii=False)
        else:
            context_str = str(context)

        # 1. Try Claude via Anthropic API
        if self.client is not None:
            try:
                user_message = (
                    f"COMPUTED FACTORY CONTEXT:\n"
                    f"```json\n{context_str}\n```\n\n"
                    f"USER QUESTION: {query}"
                )
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=600,
                    system=self.SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_message}
                    ],
                )
                if response and response.content:
                    return response.content[0].text.strip()
            except Exception as e:
                # Fallback to local rule engine if API fails
                pass

        # 2. Intelligent Deterministic Fallback Engine
        return self._rule_based_fallback(query, context if isinstance(context, dict) else {})

    def _rule_based_fallback(self, query: str, context: Dict[str, Any]) -> str:
        """
        Deterministic, rule-based answering engine when Anthropic API is unconfigured.
        Answers from computed context only, maintaining the exact guardrail:
        'Mere paas yeh data nahi hai' if query cannot be answered.
        """
        q_lower = query.lower()

        # Reorder / Purchase Orders queries
        # Keywords: order, purchase, khareed, kharid, chahiye, po, lena, kab, alert
        if any(w in q_lower for w in ["order", "purchase", "kharid", "khareed", "chahiye", "po", "kab", "alert", "mangwana"]):
            urgent = context.get("urgent_reorders", [])
            if not urgent:
                return "✅ Is hafte koi urgent order nahi karna hai. Sabhi raw materials ka stock safe level par hai."

            crit_lines = []
            for item in urgent:
                qty = int(round(item.get("recommended_qty", 0)))
                unit = item.get("unit", "")
                mname = item.get("material_name", "")
                deadline = item.get("deadline", "Turant")
                crit_lines.append(f"• **{mname}**: {qty:,} {unit} order karein by **{deadline}**")

            return (
                f"🚨 **Is hafte ye raw materials order karne hain:**\n\n"
                + "\n".join(crit_lines)
                + "\n\nInhe deadline se pehle order karein taaki production na ruke."
            )

        # Deadstock / Money Locked queries
        # Keywords: paisa, phasa, dead, stock, rokda, loss, idle, slow, capital, block
        if any(w in q_lower for w in ["paisa", "phasa", "dead", "rokda", "loss", "idle", "slow", "capital", "block", "rupee", "kaha"]):
            metrics = context.get("summary_metrics", {})
            locked_val = metrics.get("total_cash_locked_in_deadstock_rupees", 0.0)
            drain = metrics.get("annual_carrying_cost_drain_rupees", 0.0)
            top_dead = context.get("top_deadstock_items", [])

            def fmt(v):
                if v >= 100000:
                    return f"₹ {v / 100000:.2f} Lakh"
                return f"₹ {v:,.0f}"

            lines = [f"🛑 **Godam me kul {fmt(locked_val)} ka paisa dead stock me phasa hua hai.**"]
            if drain > 0:
                lines.append(f"Har saal ispar lagbhag **{fmt(drain)}** ka holding cost (interest + godown rent) lag raha hai.\n")

            if top_dead:
                lines.append("**Top items jisme paisa phasa hai:**")
                for it in top_dead[:3]:
                    name = it.get("item_name", "")
                    amt = it.get("cash_locked_rupees", 0.0)
                    idle = it.get("days_inactive", 0)
                    act = it.get("recommended_action", "")
                    lines.append(f"• **{name}**: {fmt(amt)} ({idle} din se band) — *Action: {act}*")

            return "\n".join(lines)

        # Demand / Forecast / Sales queries
        # Keywords: demand, bikri, sales, forecast, aage, agle, mahine, kitna
        if any(w in q_lower for w in ["demand", "bikri", "sales", "forecast", "aage", "agle", "mahine", "kitna"]):
            f_items = context.get("top_forecast_items", [])
            if not f_items:
                return "Mere paas yeh data nahi hai."

            lines = ["📈 **Agle 12 hafton ka demand forecast:**\n"]
            for it in f_items[:4]:
                name = it.get("product_name", "")
                tot = it.get("total_12w_demand", 0.0)
                acc = it.get("accuracy_pct", 0.0)
                lines.append(f"• **{name}**: {tot:,.0f} units (Accuracy: {acc:.1f}%)")

            return "\n".join(lines)

        # Stockout / Danger queries
        # Keywords: stockout, khatam, risk, danger, zero
        if any(w in q_lower for w in ["stockout", "khatam", "risk", "danger", "zero"]):
            urgent = context.get("urgent_reorders", [])
            if urgent:
                items_str = ", ".join(it.get("material_name", "") for it in urgent[:3])
                return f"⚠️ **Stockout Risk:** Agle 14 din me {len(urgent)} items khatam hone ka khatra hai: {items_str}."
            return "✅ Agle 14 din me kisi item ke stockout ka khatra nahi hai."

        # Strict Guardrail Fallback: If not in context or unknown query
        return "Mere paas yeh data nahi hai."
