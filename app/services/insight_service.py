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
    """Generate comprehensive AI business insights."""
    insights = []

    # 1. Executive Summary
    trend = detect_trend(forecast_data)
    forecast_values = [d["value"] for d in forecast_data]
    avg_forecast = np.mean(forecast_values) if forecast_values else 0
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
            f"Total projected revenue for the forecast period: ${total_projected:,.2f}. "
            f"The primary driver of your forecast is '{top_driver}'."
        ),
    })

    # 2. Risk Alerts
    risk_items = []
    mape = metrics.get("mape", 0)
    volatility = detect_volatility(actual_data)

    if mape > 20:
        risk_items.append(
            f"⚠️ High prediction error (MAPE: {mape}%). Model reliability is questionable. "
            "Consider providing more data or adjusting parameters."
        )
    if volatility["level"] == "High":
        risk_items.append(
            f"⚠️ High revenue volatility detected ({volatility['volatility'] * 100:.1f}%). "
            "Sudden swings may impact forecasting accuracy."
        )
    if growth_rate < -10:
        risk_items.append(
            f"⚠️ Significant projected decline ({growth_rate}%). "
            "Immediate attention required to reverse the trend."
        )

    if not risk_items:
        risk_items.append("✅ No critical risks detected. Forecast appears stable and reliable.")

    insights.append({
        "type": "risk_alerts",
        "title": "Risk Alerts",
        "icon": "🚨",
        "color": "#EF4444",
        "content": " | ".join(risk_items),
    })

    # 3. Growth Opportunities
    opportunities = []
    seasonality = detect_seasonality(actual_data)

    if growth_rate > 0:
        opportunities.append(
            f"📈 Positive growth trajectory ({growth_rate}%). "
            "Consider scaling marketing efforts to capitalize on momentum."
        )
    if seasonality["detected"]:
        opportunities.append(
            f"🔄 {seasonality['description']} "
            "Align inventory and campaigns with peak periods."
        )
    if accuracy > 85:
        opportunities.append(
            "🎯 High model accuracy enables confident resource allocation. "
            "Use forecasts to optimize staffing and inventory."
        )

    if not opportunities:
        opportunities.append(
            "💡 Focus on data quality improvements and collecting more historical data "
            "to unlock better forecasting capabilities."
        )

    insights.append({
        "type": "growth_opportunities",
        "title": "Growth Opportunities",
        "icon": "🚀",
        "color": "#10B981",
        "content": " | ".join(opportunities),
    })

    # 4. Inventory Optimization
    if forecast_values:
        max_demand = max(forecast_values)
        min_demand = min(forecast_values)
        avg_demand = np.mean(forecast_values)
        safety_stock = round(avg_demand * 0.2, 2)

        insights.append({
            "type": "inventory_optimization",
            "title": "Inventory Optimization",
            "icon": "📦",
            "color": "#F59E0B",
            "content": (
                f"Projected demand range: ${min_demand:,.2f} – ${max_demand:,.2f}. "
                f"Average forecast: ${avg_demand:,.2f}. "
                f"Recommended safety stock level: ${safety_stock:,.2f} "
                f"(20% buffer above average). "
                f"Demand volatility is {volatility['level'].lower()}, "
                f"{'requiring a larger safety margin.' if volatility['level'] == 'High' else 'supporting lean inventory management.'}"
            ),
        })

    return insights
