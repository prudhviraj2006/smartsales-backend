"""
Chat Service – AI Business Assistant.
Uses forecast context to provide intelligent responses.
"""
import json
from typing import Dict, Any, List, Optional
import numpy as np


# Pre-defined response patterns for offline AI chat (no API key needed)
KNOWLEDGE_BASE = {
    "forecast": "Based on the current forecast, {trend_description}. The model predicts {growth_text} with {accuracy}% accuracy.",
    "accuracy": "The model's MAPE is {mape}%, which means the average prediction error is about {mape}% of the actual values. {accuracy_assessment}",
    "revenue": "Projected total revenue for the forecast period is {projected_revenue}. {revenue_trend}",
    "risk": "Current risk assessment: {risk_level}. {risk_detail}",
    "strategy": "{strategy_recommendation}",
    "seasonality": "{seasonality_info}",
    "model": "You are currently using the {model_type} model. {model_description}",
}

STRATEGY_TEMPLATES = [
    "Consider diversifying revenue streams to reduce dependency on seasonal peaks.",
    "Focus on customer retention strategies – a 5% increase in retention can boost profits by 25-95%.",
    "Analyze your top-performing products/services and allocate more resources to scale them.",
    "Implement dynamic pricing strategies based on demand forecast patterns.",
    "Build strategic inventory buffers ahead of projected high-demand periods.",
    "Invest in marketing during projected low periods to smooth revenue cycles.",
]

MODEL_DESCRIPTIONS = {
    "prophet": "Prophet (by Meta) excels at capturing trends and seasonality in your data. It's particularly good with daily/weekly patterns and handles outliers well.",
    "lightgbm": "LightGBM is a gradient boosting model that uses lag features, rolling averages, and date features. It often provides higher accuracy for complex patterns.",
}


def classify_intent(message: str) -> str:
    """Simple intent classification."""
    msg = message.lower()
    if any(w in msg for w in ["forecast", "predict", "projection", "future"]):
        return "forecast"
    if any(w in msg for w in ["accuracy", "error", "mape", "mae", "rmse", "reliable"]):
        return "accuracy"
    if any(w in msg for w in ["revenue", "sales", "income", "money", "profit"]):
        return "revenue"
    if any(w in msg for w in ["risk", "danger", "warning", "concern", "worry"]):
        return "risk"
    if any(w in msg for w in ["strategy", "advice", "recommend", "suggest", "improve", "how to", "what should"]):
        return "strategy"
    if any(w in msg for w in ["seasonal", "pattern", "cycle", "trend"]):
        return "seasonality"
    if any(w in msg for w in ["model", "prophet", "lightgbm", "algorithm"]):
        return "model"
    return "general"


def format_currency(value: float, symbol: str = "₹") -> str:
    """Helper to format currency with symbol and L/Cr suffixes."""
    abs_val = abs(value)
    if abs_val >= 10000000: # 1 Crore
        return f"{symbol}{value / 10000000:.2f} Cr"
    if abs_val >= 100000: # 1 Lakh
        return f"{symbol}{value / 100000:.2f} L"
    return f"{symbol}{value:,.2f}"


def generate_response(
    message: str,
    forecast_context: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict]] = None,
) -> str:
    """Generate an AI response based on forecast context."""
    intent = classify_intent(message)

    if forecast_context is None:
        # Fallback for when no data is loaded yet
        if intent == "general":
            return (
                "👋 Hello! I'm your SmartSales AI Assistant. I don't have your specific business data yet, "
                "but I can help you with general sales forecasting concepts or guide you on how to upload your data.\n\n"
                "To get started, please **Upload a CSV** in the 'Upload' tab and **Train a Model**!"
            )
        elif intent == "strategy":
            import random
            advice = random.choice(STRATEGY_TEMPLATES)
            return (
                f"While I don't have your specific data yet, here is a general business strategy: {advice}\n\n"
                "Once you upload your sales history, I can provide much more tailored recommendations!"
            )
        else:
            return (
                "I don't have any forecast data loaded yet. "
                "Please upload your data and run a forecast first, "
                "then I can provide intelligent business insights and specific details about your " + intent + "!"
            )

    # Extract context (rest of the logic remains the same)
    growth_rate = forecast_context.get("growth_rate", 0)
    accuracy = forecast_context.get("accuracy", 0)
    mape = forecast_context.get("mape", 0)
    projected_revenue = forecast_context.get("projected_revenue", 0)
    model_type = forecast_context.get("model_type", "unknown")
    top_driver = forecast_context.get("top_driver", "Unknown")
    currency_symbol = forecast_context.get("currency_symbol", "₹")

    # Trend
    trend_description = (
        f"revenue is expected to grow by {growth_rate}%"
        if growth_rate > 0
        else f"revenue may decline by {abs(growth_rate)}%"
        if growth_rate < 0
        else "revenue is expected to remain stable"
    )
    growth_text = "growth" if growth_rate > 0 else "decline" if growth_rate < 0 else "stability"

    # Accuracy assessment
    if accuracy > 90:
        accuracy_assessment = "This is excellent – you can rely on these forecasts with high confidence."
    elif accuracy > 80:
        accuracy_assessment = "This is good. The forecasts are reliable for strategic planning."
    elif accuracy > 70:
        accuracy_assessment = "This is acceptable but there's room for improvement. Consider adding more historical data."
    else:
        accuracy_assessment = "This accuracy level suggests significant uncertainty. Use forecasts as directional indicators only."

    # Risk
    risk_level = "Low" if accuracy > 85 and abs(growth_rate) < 20 else "Medium" if accuracy > 70 else "High"
    risk_detail = {
        "Low": "Your forecasts appear stable and reliable. Continue monitoring for any sudden changes.",
        "Medium": "Some uncertainty exists. Keep an eye on key metrics and have contingency plans ready.",
        "High": "Significant uncertainty detected. Recommend detailed analysis and conservative planning.",
    }[risk_level]

    # Revenue trend
    revenue_trend = (
        f"With a growth rate of {growth_rate}%, this represents a positive outlook."
        if growth_rate > 0
        else f"The projected decline of {abs(growth_rate)}% warrants attention."
        if growth_rate < 0
        else "Revenue is projected to remain consistent."
    )

    # Seasonality
    seasonality_info = (
        f"The primary driver of your forecast is '{top_driver}'. "
        "This suggests seasonal patterns play a significant role in your business. "
        "Align your operations and marketing with these cycles for optimal results."
    )

    # Model
    model_description = MODEL_DESCRIPTIONS.get(model_type, "Model details not available.")

    # Strategy
    import random
    strategy_recommendation = random.choice(STRATEGY_TEMPLATES) + (
        f" Given your {growth_rate}% growth projection and {accuracy}% accuracy, "
        f"the key driver '{top_driver}' suggests focusing your efforts there."
    )

    # Format response
    context = {
        "trend_description": trend_description,
        "growth_text": growth_text,
        "accuracy": accuracy,
        "mape": mape,
        "accuracy_assessment": accuracy_assessment,
        "projected_revenue": format_currency(projected_revenue, currency_symbol),
        "risk_level": risk_level,
        "risk_detail": risk_detail,
        "revenue_trend": revenue_trend,
        "strategy_recommendation": strategy_recommendation,
        "seasonality_info": seasonality_info,
        "model_type": model_type,
        "model_description": model_description,
    }

    if intent in KNOWLEDGE_BASE:
        try:
            response = KNOWLEDGE_BASE[intent].format(**context)
        except (KeyError, IndexError):
            response = f"Based on your {model_type} forecast: {trend_description} with {accuracy}% accuracy."
    else:
        # General response
        response = (
            f"Great question! Here's what I can tell you based on your {model_type} forecast:\n\n"
            f"• **Trend**: {trend_description}\n"
            f"• **Accuracy**: {accuracy}% (MAPE: {mape}%)\n"
            f"• **Projected Revenue**: {format_currency(projected_revenue, currency_symbol)}\n"
            f"• **Key Driver**: {top_driver}\n\n"
            f"Is there something specific you'd like to dive deeper into? "
            f"I can help with risk analysis, strategy recommendations, or model details."
        )

    return response
