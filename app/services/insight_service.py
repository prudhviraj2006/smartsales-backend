"""
AI Insight Service – Generates business insights from forecast data.
"""
import numpy as np
from typing import Dict, Any, List


def detect_trend(forecast_data: list) -> str:
    """Detect overall trend direction."""
    if len(forecast_data) < 2:
        return "stable"
    values = [d["value"] for d in forecast_data]
    first_half = np.mean(values[: len(values) // 2])
    second_half = np.mean(values[len(values) // 2 :])
    change = ((second_half - first_half) / first_half * 100) if first_half != 0 else 0
    if change > 5:
        return "upward"
    elif change < -5:
        return "downward"
    return "stable"


def detect_seasonality(actual_data: list) -> Dict[str, Any]:
    """Detect seasonal patterns in historical data."""
    if len(actual_data) < 60:
        return {"detected": False, "description": "Insufficient data for seasonality detection."}

    values = [d["value"] for d in actual_data]
    monthly_values = []
    chunk_size = max(1, len(values) // 12)
    for i in range(0, len(values), chunk_size):
        monthly_values.append(np.mean(values[i : i + chunk_size]))

    if len(monthly_values) < 3:
        return {"detected": False, "description": "Not enough monthly data points."}

    cv = np.std(monthly_values) / np.mean(monthly_values) if np.mean(monthly_values) != 0 else 0
    if cv > 0.15:
        peak_idx = int(np.argmax(monthly_values))
        return {
            "detected": True,
            "description": f"Strong seasonal pattern detected. Peak activity around period {peak_idx + 1}.",
            "coefficient_of_variation": round(cv, 4),
        }
    return {"detected": False, "description": "No significant seasonality detected."}


def detect_volatility(actual_data: list) -> Dict[str, Any]:
    """Assess data volatility."""
    values = [d["value"] for d in actual_data]
    returns = np.diff(values) / np.array(values[:-1]) if len(values) > 1 else [0]
    vol = float(np.std(returns))
    if vol > 0.1:
        level = "High"
    elif vol > 0.05:
        level = "Medium"
    else:
        level = "Low"

    return {
        "level": level,
        "volatility": round(vol, 4),
        "description": f"{level} volatility detected ({round(vol * 100, 2)}%). "
        + (
            "Consider risk mitigation strategies."
            if level == "High"
            else "Revenue stream appears relatively stable."
            if level == "Low"
            else "Some fluctuation is expected."
        ),
    }


def generate_insights(
    forecast_data: list,
    actual_data: list,
    metrics: Dict[str, Any],
    growth_rate: float,
    accuracy: float,
    top_driver: str,
    model_type: str,
) -> List[Dict[str, Any]]:
    """Generate comprehensive AI business insights using GPT-4o if available."""
    from app.core.config import settings
    
    # Check if OpenAI API key is available
    if settings.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""
            As an expert business analyst, provide detailed insights based on the following sales forecast data:
            - Model Type: {model_type}
            - Forecast Accuracy: {accuracy}% (MAPE: {metrics.get('mape', 'N/A')}%)
            - Projected Growth Rate: {growth_rate}%
            - Top Influencing Factor: {top_driver}
            - Metrics: {metrics}
            - Sample Forecast Values: {forecast_data[:10]}...
            
            Please provide exactly 4 sections:
            1. Executive Summary (2-3 sentences summarising the outlook)
            2. Risk Warnings (based on forecast volatility and accuracy)
            3. Growth Recommendations (how to capitalize on trends)
            4. Inventory/Resource Planning (specific suggestions based on demand)
            
            Return the response in a structured format that I can parse.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a professional business analyst providing strategic insights based on forecast data. Be concise, actionable, and data-driven."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.choices[0].message.content
            # Note: In a real app, you'd parse this more robustly. 
            # For this demo, we'll split by sections or use a fallback if parsing fails.
            
            # Simple parsing logic (assuming GPT returns sections with headers)
            sections = content.split("\n\n")
            
            insights = []
            types = ["executive_summary", "risk_warnings", "growth_recommendations", "inventory_planning"]
            titles = ["Executive Summary", "Risk Warnings", "Growth Recommendations", "Inventory/Resource Planning"]
            icons = ["📊", "🚨", "🚀", "📦"]
            colors = ["#3B82F6", "#EF4444", "#10B981", "#F59E0B"]
            
            for i, section in enumerate(sections[:4]):
                # Remove header if exists (e.g. "1. Executive Summary:")
                clean_content = section.split(":", 1)[-1].strip() if ":" in section else section.strip()
                insights.append({
                    "type": types[i],
                    "title": titles[i],
                    "icon": icons[i],
                    "color": colors[i],
                    "content": clean_content
                })
            
            if len(insights) >= 4:
                return insights
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            # Fallback to rule-based insights if OpenAI fails

    # --- Rule-based Fallback (Enhanced) ---
    insights = []

    # 1. Executive Summary
    trend = detect_trend(forecast_data)
    forecast_values = [d["value"] for d in forecast_data]
    total_projected = sum(forecast_values)

    trend_desc = {
        "upward": "showing positive growth momentum",
        "downward": "indicating a declining pattern",
        "stable": "maintaining a consistent level",
    }

    insights.append({
        "type": "executive_summary",
        "title": "Executive Summary",
        "icon": "📊",
        "color": "#3B82F6",
        "content": (
            f"Based on {model_type.upper()} analysis, your business is {trend_desc.get(trend, 'stable')} "
            f"with a projected growth rate of {growth_rate}%. "
            f"Model accuracy stands at {accuracy}% (MAPE: {metrics.get('mape', 'N/A')}%). "
            f"Total projected revenue: ${total_projected:,.2f}. "
            f"The primary driver is '{top_driver}'."
        ),
    })

    # 2. Risk Warnings
    risk_items = []
    mape = metrics.get("mape", 0)
    volatility = detect_volatility(actual_data)

    if mape > 20:
        risk_items.append(f"⚠️ High prediction error ({mape}%). Reliability is low.")
    if volatility["level"] == "High":
        risk_items.append(f"⚠️ High volatility ({volatility['volatility'] * 100:.1f}%).")
    if growth_rate < -10:
        risk_items.append(f"⚠️ Significant decline ({growth_rate}%).")

    insights.append({
        "type": "risk_warnings",
        "title": "Risk Warnings",
        "icon": "🚨",
        "color": "#EF4444",
        "content": " | ".join(risk_items) if risk_items else "✅ No critical risks detected.",
    })

    # 3. Growth Recommendations
    opportunities = []
    seasonality = detect_seasonality(actual_data)

    if growth_rate > 0:
        opportunities.append(f"📈 Positive growth ({growth_rate}%). Scale marketing.")
    if seasonality["detected"]:
        opportunities.append(f"🔄 Seasonality detected. Align inventory with peaks.")
    if accuracy > 85:
        opportunities.append("🎯 High accuracy. Confidently allocate resources.")

    insights.append({
        "type": "growth_recommendations",
        "title": "Growth Recommendations",
        "icon": "🚀",
        "color": "#10B981",
        "content": " | ".join(opportunities) if opportunities else "💡 Focus on data quality improvements.",
    })

    # 4. Inventory Planning
    if forecast_values:
        avg_demand = np.mean(forecast_values)
        safety_stock = round(avg_demand * 0.2, 2)
        insights.append({
            "type": "inventory_planning",
            "title": "Inventory Planning",
            "icon": "📦",
            "color": "#F59E0B",
            "content": f"Avg demand: ${avg_demand:,.2f}. Safety stock: ${safety_stock:,.2f} (20% buffer).",
        })

    return insights
