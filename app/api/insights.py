"""
Insights API Router – Generate AI business insights.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.schemas import ForecastResult, ModelMetric
from app.services.insight_service import generate_insights

router = APIRouter(prefix="/api", tags=["Insights"])


@router.get("/insights")
def get_insights(
    forecast_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get forecast
    query = db.query(ForecastResult).filter(
        ForecastResult.user_id == current_user["user_id"]
    )
    if forecast_id:
        query = query.filter(ForecastResult.id == forecast_id)

    forecast = query.order_by(ForecastResult.created_at.desc()).first()

    if not forecast:
        raise HTTPException(status_code=404, detail="No forecast found. Train a model first.")

    # Get metrics
    metric = (
        db.query(ModelMetric)
        .filter(ModelMetric.forecast_id == forecast.id)
        .first()
    )
    metrics = {}
    if metric:
        metrics = {
            "mae": metric.mae,
            "rmse": metric.rmse,
            "mape": metric.mape,
            "r2_score": metric.r2_score,
            "mean_error": metric.mean_error,
            "std_error": metric.std_error,
        }

    insights = generate_insights(
        forecast_data=forecast.forecast_data or [],
        actual_data=forecast.actual_data or [],
        metrics=metrics,
        growth_rate=forecast.growth_rate or 0,
        accuracy=forecast.accuracy or 0,
        top_driver=forecast.top_driver or "Unknown",
        model_type=forecast.model_type or "unknown",
    )

    return {
        "forecast_id": forecast.id,
        "model_type": forecast.model_type,
        "insights": insights,
    }
