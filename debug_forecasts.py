import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models.schemas import ForecastResult, ModelMetric, UploadedFile

db = SessionLocal()
try:
    print("=== FILES ===")
    files = db.query(UploadedFile).all()
    for f in files:
        print(f"ID: {f.id}, Filename: {f.filename}, Target Col: {f.target_column}, Date Col: {f.date_column}")

    print("\n=== FORECAST RESULTS ===")
    forecasts = db.query(ForecastResult).order_by(ForecastResult.created_at.desc()).all()
    for f in forecasts:
        print(f"ID: {f.id}, Model: {f.model_type}, Acc: {f.accuracy}, Projected Rev: {f.projected_revenue}, Growth Rate: {f.growth_rate}, Top Driver: {f.top_driver}, Actuals Count: {len(f.actual_data or [])}, Forecasts Count: {len(f.forecast_data or [])}")

    print("\n=== MODEL METRICS ===")
    metrics = db.query(ModelMetric).all()
    for m in metrics:
        print(f"ID: {m.id}, Forecast ID: {m.forecast_id}, Model: {m.model_type}, MAE: {m.mae}, RMSE: {m.rmse}, MAPE: {m.mape}")
finally:
    db.close()
