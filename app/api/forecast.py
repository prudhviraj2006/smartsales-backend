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

from typing import Optional, Union, Any

router = APIRouter(prefix="/api", tags=["Forecast"])


from pydantic import BaseModel, field_validator

class TrainRequest(BaseModel):
    file_id: Optional[Union[int, str]] = None
    target_column: Optional[str] = None
    targetColumn: Optional[str] = None
    aggregation: Optional[str] = "daily"
    aggregationLevel: Optional[str] = None
    horizon_months: Optional[int] = 6
    forecastHorizon: Optional[int] = None
    model_type: Optional[str] = "lightgbm"
    model: Optional[str] = None

    @field_validator('model', 'model_type', mode='before')
    @classmethod
    def normalize_model(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator('aggregation', 'aggregationLevel', mode='before')
    @classmethod
    def normalize_agg(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v


@router.post("/train")
def train_forecast(
    req: TrainRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_col = req.target_column or req.targetColumn
    agg_level = (req.aggregationLevel or req.aggregation or "daily").lower()
    horizon = req.forecastHorizon or req.horizon_months or 6
    model = (req.model or req.model_type or "lightgbm").lower()

    if not target_col:
        raise HTTPException(status_code=400, detail="target_column parameter is required")

    print("📨 Training request received:", req.model_dump())
    print(f"🔨 Starting model training for target '{target_col}', model '{model}', agg '{agg_level}', horizon {horizon}mo...")

    # Get uploaded file with robust ID parsing and fallback to latest upload
    parsed_file_id = None
    if req.file_id is not None:
        try:
            clean_str = str(req.file_id).replace("job_", "").replace("file_", "")
            parsed_file_id = int(clean_str)
        except (ValueError, TypeError):
            pass

    uploaded = None
    if parsed_file_id is not None:
        uploaded = (
            db.query(UploadedFile)
            .filter(
                UploadedFile.id == parsed_file_id,
                UploadedFile.user_id == current_user["user_id"],
            )
            .first()
        )

    if not uploaded:
        # Fallback to the latest file uploaded by this user
        uploaded = (
            db.query(UploadedFile)
            .filter(UploadedFile.user_id == current_user["user_id"])
            .order_by(UploadedFile.id.desc())
            .first()
        )

    if not uploaded:
        raise HTTPException(status_code=404, detail="No uploaded CSV file found for training. Please upload a file first.")

    # Read CSV
    try:
        df = pd.read_csv(uploaded.file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    # Validate target column
    if target_col not in df.columns:
        raise HTTPException(
            status_code=400, detail=f"Column '{target_col}' not found in dataset. Available columns: {list(df.columns)}"
        )

    # Update target column
    uploaded.target_column = target_col
    db.commit()

    # Train model
    try:
        result = train_model(
            df=df,
            date_col=uploaded.date_column,
            target_col=target_col,
            model_type=model,
            aggregation=agg_level,
            horizon_months=horizon,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

    # Also train alternate model to record metrics for Prophet vs LightGBM comparison
    alt_model_type = "prophet" if model == "lightgbm" else "lightgbm"
    alt_result = None
    try:
        alt_result = train_model(
            df=df,
            date_col=uploaded.date_column,
            target_col=target_col,
            model_type=alt_model_type,
            aggregation=agg_level,
            horizon_months=horizon,
        )
    except Exception as alt_err:
        print(f"[FORECAST API] Alternate model training warning: {alt_err}")

    # Save forecast result
    try:
        forecast = ForecastResult(
            user_id=current_user["user_id"],
            file_id=uploaded.id,
            model_type=model,
            aggregation=agg_level,
            horizon_months=horizon,
            forecast_data=result["forecast_data"],
            actual_data=result["actual_data"],
            projected_revenue=result["projected_revenue"],
            growth_rate=result["growth_rate"],
            accuracy=result["accuracy"],
            top_driver=result["top_driver"],
            confidence_lower=result["confidence_lower"],
            confidence_upper=result["confidence_upper"],
            decomposition=result.get("decomposition"),
            currency_symbol=result.get("currency_symbol", "₹"),
        )
        db.add(forecast)
        db.commit()
        db.refresh(forecast)
    except Exception as e:
        db.rollback()
        print(f"[FORECAST API ERROR] Failed to save ForecastResult: {e}")
        raise HTTPException(status_code=500, detail=f"Database error saving forecast: {str(e)}")

    # Save primary metrics
    try:
        metrics_data = result["metrics"]
        metric = ModelMetric(
            forecast_id=forecast.id,
            model_type=model,
            mae=metrics_data["mae"],
            rmse=metrics_data["rmse"],
            mape=metrics_data["mape"],
            r2_score=metrics_data["r2_score"],
            mean_error=metrics_data["mean_error"],
            std_error=metrics_data["std_error"],
            residuals=metrics_data["residuals"],
        )
        db.add(metric)

        # Save alternate model metrics if available
        if alt_result and "metrics" in alt_result:
            alt_metrics_data = alt_result["metrics"]
            alt_metric = ModelMetric(
                forecast_id=forecast.id,
                model_type=alt_model_type,
                mae=alt_metrics_data["mae"],
                rmse=alt_metrics_data["rmse"],
                mape=alt_metrics_data["mape"],
                r2_score=alt_metrics_data["r2_score"],
                mean_error=alt_metrics_data["mean_error"],
                std_error=alt_metrics_data["std_error"],
                residuals=alt_metrics_data["residuals"],
            )
            db.add(alt_metric)

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[FORECAST API ERROR] Failed to save ModelMetric: {e}")
        raise HTTPException(status_code=500, detail=f"Database error saving metrics: {str(e)}")

    print("✅ Training completed. Calculating metrics...")
    print("📊 Raw metrics:", {
        "mae": metrics_data["mae"],
        "rmse": metrics_data["rmse"],
        "mape": metrics_data["mape"],
        "accuracy": result["accuracy"],
    })
    print("📅 Forecast horizon:", horizon)
    print("💰 Projected revenue:", result["projected_revenue"])
    print("🎯 Top driver:", result["top_driver"])
    print(f"📈 Chart data points: {len(result['actual_data'])} actuals / {len(result['forecast_data'])} forecasts")

    response_payload = {
        "success": True,
        "jobId": f"job_{forecast.id}",
        "forecast_id": forecast.id,
        "id": forecast.id,
        "model": model.upper(),
        "model_type": model,
        "modelType": model,
        "aggregation": agg_level,
        "aggregationLevel": agg_level,
        "forecastHorizon": horizon,
        "horizon_months": horizon,
        "metrics": {
            "mae": metrics_data["mae"],
            "rmse": metrics_data["rmse"],
            "mape": metrics_data["mape"],
            "accuracy": result["accuracy"],
        },
        "mae": metrics_data["mae"],
        "rmse": metrics_data["rmse"],
        "mape": metrics_data["mape"],
        "accuracy": result["accuracy"],
        "projectedRevenue": result["projected_revenue"],
        "projected_revenue": result["projected_revenue"],
        "growthRate": result["growth_rate"],
        "growth_rate": result["growth_rate"],
        "topDriver": result["top_driver"],
        "top_driver": result["top_driver"],
        "chartData": {
            "trends": result["actual_data"],
            "forecast": result["forecast_data"],
        },
        "actual_data": result["actual_data"],
        "forecast_data": result["forecast_data"],
        "confidence_lower": result["confidence_lower"],
        "confidence_upper": result["confidence_upper"],
        "decomposition": result.get("decomposition"),
        "currency_symbol": result.get("currency_symbol", "₹"),
        "message": f"{model.upper()} model trained successfully!",
    }

    print("📤 SENDING RESPONSE TO FRONTEND (Keys):", list(response_payload.keys()))
    return response_payload


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

    metric = (
        db.query(ModelMetric)
        .filter(
            ModelMetric.forecast_id == forecast.id,
            ModelMetric.model_type == forecast.model_type
        )
        .first()
    )

    if not metric:
        metric = (
            db.query(ModelMetric)
            .filter(ModelMetric.forecast_id == forecast.id)
            .first()
        )

    mae = metric.mae if metric else 0.0
    rmse = metric.rmse if metric else 0.0
    mape = metric.mape if metric else 0.0
    calc_acc = forecast.accuracy if (forecast.accuracy is not None and forecast.accuracy > 0) else (round(100 - mape, 2) if mape else 85.0)

    print(f"[FORECAST API DIAGNOSTIC] GET /forecast -> id={forecast.id}, model={forecast.model_type}, accuracy={calc_acc}, horizon={forecast.horizon_months}, mae={mae}, rmse={rmse}, mape={mape}")

    return {
        "success": True,
        "jobId": f"job_{forecast.id}",
        "forecast_id": forecast.id,
        "id": forecast.id,
        "model": (forecast.model_type or "lightgbm").upper(),
        "model_type": forecast.model_type,
        "modelType": forecast.model_type,
        "aggregation": forecast.aggregation,
        "aggregationLevel": forecast.aggregation,
        "forecastHorizon": forecast.horizon_months or 6,
        "horizon_months": forecast.horizon_months or 6,
        "metrics": {
            "mae": mae,
            "rmse": rmse,
            "mape": mape,
            "accuracy": calc_acc,
        },
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "accuracy": calc_acc,
        "projectedRevenue": forecast.projected_revenue,
        "projected_revenue": forecast.projected_revenue,
        "growthRate": forecast.growth_rate,
        "growth_rate": forecast.growth_rate,
        "topDriver": forecast.top_driver,
        "top_driver": forecast.top_driver,
        "chartData": {
            "trends": forecast.actual_data or [],
            "forecast": forecast.forecast_data or [],
        },
        "actual_data": forecast.actual_data or [],
        "forecast_data": forecast.forecast_data or [],
        "confidence_lower": forecast.confidence_lower or [],
        "confidence_upper": forecast.confidence_upper or [],
        "decomposition": forecast.decomposition,
        "currency_symbol": getattr(forecast, "currency_symbol", "₹"),
        "created_at": forecast.created_at.isoformat() if forecast.created_at else None,
    }


@router.get("/metrics")
def get_metrics(
    forecast_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_forecast = None
    if not forecast_id:
        target_forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.user_id == current_user["user_id"])
            .order_by(ForecastResult.created_at.desc())
            .first()
        )
        if not target_forecast:
            raise HTTPException(status_code=404, detail="No forecast found")
        forecast_id = target_forecast.id
    else:
        target_forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.id == forecast_id)
            .first()
        )

    metrics = (
        db.query(ModelMetric)
        .filter(ModelMetric.forecast_id == forecast_id)
        .all()
    )

    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics found")

    calc_acc = target_forecast.accuracy if target_forecast and target_forecast.accuracy is not None else 0
    print(f"[FORECAST API DIAGNOSTIC] GET /metrics for forecast_id={forecast_id} -> metric count={len(metrics)}, calc_acc={calc_acc}")

    return [
        {
            "id": m.id,
            "model_type": m.model_type,
            "mae": m.mae,
            "rmse": m.rmse,
            "mape": m.mape,
            "accuracy": round(100 - m.mape, 2) if m.mape is not None else calc_acc,
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
        model_type=forecast.model_type,
        currency_symbol=getattr(forecast, "currency_symbol", "₹")
    )

    pdf_buffer = generate_forecast_pdf(forecast, metric, insights, req.chart_image)
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{forecast.id}.pdf"}
    )
