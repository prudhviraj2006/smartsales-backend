"""
Forecast API Router – Train models, get forecasts & metrics.
"""
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.schemas import UploadedFile, ForecastResult, ModelMetric
from app.services.ml_service import train_model
from app.services.export_service import generate_forecast_csv, generate_forecast_pdf
from app.services.insight_service import generate_insights

router = APIRouter(prefix="/api", tags=["Forecast"])


class TrainRequest(BaseModel):
    file_id: int
    target_column: str
    aggregation: str = "daily"  # daily, weekly, monthly
    horizon_months: int = 6
    model_type: str = "lightgbm"  # prophet, lightgbm


@router.post("/train")
def train_forecast(
    req: TrainRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get uploaded file
    uploaded = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == req.file_id,
            UploadedFile.user_id == current_user["user_id"],
        )
        .first()
    )
    if not uploaded:
        raise HTTPException(status_code=404, detail="File not found")

    # Read CSV
    try:
        df = pd.read_csv(uploaded.file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    # Validate target column
    if req.target_column not in df.columns:
        raise HTTPException(
            status_code=400, detail=f"Column '{req.target_column}' not found in data"
        )

    # Update target column
    uploaded.target_column = req.target_column
    db.commit()

    # Train model
    try:
        result = train_model(
            df=df,
            date_col=uploaded.date_column,
            target_col=req.target_column,
            model_type=req.model_type,
            aggregation=req.aggregation,
            horizon_months=req.horizon_months,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

    # Save forecast result
    forecast = ForecastResult(
        user_id=current_user["user_id"],
        file_id=req.file_id,
        model_type=req.model_type,
        aggregation=req.aggregation,
        horizon_months=req.horizon_months,
        forecast_data=result["forecast_data"],
        actual_data=result["actual_data"],
        projected_revenue=result["projected_revenue"],
        growth_rate=result["growth_rate"],
        accuracy=result["accuracy"],
        top_driver=result["top_driver"],
        confidence_lower=result["confidence_lower"],
        confidence_upper=result["confidence_upper"],
        decomposition=result.get("decomposition"),
    )
    db.add(forecast)
    db.commit()
    db.refresh(forecast)

    # Save metrics
    metrics_data = result["metrics"]
    metric = ModelMetric(
        forecast_id=forecast.id,
        model_type=req.model_type,
        mae=metrics_data["mae"],
        rmse=metrics_data["rmse"],
        mape=metrics_data["mape"],
        r2_score=metrics_data["r2_score"],
        mean_error=metrics_data["mean_error"],
        std_error=metrics_data["std_error"],
        residuals=metrics_data["residuals"],
    )
    db.add(metric)
    db.commit()

    return {
        "forecast_id": forecast.id,
        "model_type": req.model_type,
        "projected_revenue": result["projected_revenue"],
        "growth_rate": result["growth_rate"],
        "accuracy": result["accuracy"],
        "top_driver": result["top_driver"],
        "message": f"{req.model_type.upper()} model trained successfully!",
    }


@router.get("/forecast")
def get_forecast(
    forecast_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ForecastResult).filter(
        ForecastResult.user_id == current_user["user_id"]
    )
    if forecast_id:
        query = query.filter(ForecastResult.id == forecast_id)

    forecast = query.order_by(ForecastResult.created_at.desc()).first()

    if not forecast:
        raise HTTPException(status_code=404, detail="No forecast found")

    return {
        "id": forecast.id,
        "model_type": forecast.model_type,
        "aggregation": forecast.aggregation,
        "horizon_months": forecast.horizon_months,
        "forecast_data": forecast.forecast_data,
        "actual_data": forecast.actual_data,
        "projected_revenue": forecast.projected_revenue,
        "growth_rate": forecast.growth_rate,
        "accuracy": forecast.accuracy,
        "top_driver": forecast.top_driver,
        "confidence_lower": forecast.confidence_lower,
        "confidence_upper": forecast.confidence_upper,
        "decomposition": forecast.decomposition,
        "created_at": forecast.created_at.isoformat() if forecast.created_at else None,
    }


@router.get("/metrics")
def get_metrics(
    forecast_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Get latest forecast if no ID
    if not forecast_id:
        forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.user_id == current_user["user_id"])
            .order_by(ForecastResult.created_at.desc())
            .first()
        )
        if not forecast:
            raise HTTPException(status_code=404, detail="No forecast found")
        forecast_id = forecast.id

    metrics = (
        db.query(ModelMetric)
        .filter(ModelMetric.forecast_id == forecast_id)
        .all()
    )

    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics found")

    return [
        {
            "id": m.id,
            "model_type": m.model_type,
            "mae": m.mae,
            "rmse": m.rmse,
            "mape": m.mape,
            "r2_score": m.r2_score,
            "mean_error": m.mean_error,
            "std_error": m.std_error,
            "residuals": m.residuals,
        }
        for m in metrics
    ]

@router.get("/export/csv")
def export_csv(
    forecast_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ForecastResult).filter(ForecastResult.user_id == current_user["user_id"])
    if forecast_id:
        query = query.filter(ForecastResult.id == forecast_id)
    
    forecast = query.order_by(ForecastResult.created_at.desc()).first()
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")

    csv_content = generate_forecast_csv(forecast)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=forecast_{forecast.id}.csv"}
    )

class PDFRequest(BaseModel):
    forecast_id: int = None
    chart_image: str = None # Base64 string

@router.post("/export/pdf")
def export_pdf(
    req: PDFRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ForecastResult).filter(ForecastResult.user_id == current_user["user_id"])
    if req.forecast_id:
        query = query.filter(ForecastResult.id == req.forecast_id)
    
    forecast = query.order_by(ForecastResult.created_at.desc()).first()
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")

    # Get metrics
    metric = db.query(ModelMetric).filter(ModelMetric.forecast_id == forecast.id).first()
    
    # Get insights
    insights = generate_insights(
        forecast_data=forecast.forecast_data,
        actual_data=forecast.actual_data,
        metrics={"mape": metric.mape if metric else 0},
        growth_rate=forecast.growth_rate,
        accuracy=forecast.accuracy,
        top_driver=forecast.top_driver,
        model_type=forecast.model_type
    )

    pdf_buffer = generate_forecast_pdf(forecast, metric, insights, req.chart_image)
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{forecast.id}.pdf"}
    )
