"""
Chat API Router – AI Business Assistant.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.schemas import ForecastResult, ModelMetric, ChatMessage
from app.services.chat_service import generate_response

router = APIRouter(prefix="/api", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    forecast_id: Optional[int] = None


@router.post("/chat")
def chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    # Build forecast context
    forecast_context = None
    forecast_id = req.forecast_id
    forecast = None

    if forecast_id:
        forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.id == forecast_id, ForecastResult.user_id == user_id)
            .first()
        )
    if not forecast:
        forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.user_id == user_id)
            .order_by(ForecastResult.created_at.desc())
            .first()
        )

    if forecast:
        forecast_id = forecast.id
        metric = (
            db.query(ModelMetric)
            .filter(ModelMetric.forecast_id == forecast.id)
            .first()
        )
        forecast_context = {
            "model_type": forecast.model_type,
            "growth_rate": forecast.growth_rate or 0,
            "accuracy": forecast.accuracy or 0,
            "projected_revenue": forecast.projected_revenue or 0,
            "top_driver": forecast.top_driver or "Unknown",
            "mape": metric.mape if metric else 0,
            "currency_symbol": getattr(forecast, "currency_symbol", "₹"),
        }

    print(f"[CHAT API DIAGNOSTIC] User '{user_id}' query: '{req.message[:30]}...' -> Forecast context found: {forecast_context is not None}")

    # Get chat history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    chat_history = [
        {"role": h.role, "message": h.message} for h in reversed(history)
    ]

    # Generate response
    response = generate_response(
        message=req.message,
        forecast_context=forecast_context,
        chat_history=chat_history,
    )

    # Save messages
    user_msg = ChatMessage(
        user_id=user_id,
        forecast_id=forecast_id,
        role="user",
        message=req.message,
    )
    ai_msg = ChatMessage(
        user_id=user_id,
        forecast_id=forecast_id,
        role="assistant",
        message=response,
    )
    db.add(user_msg)
    db.add(ai_msg)
    db.commit()

    return {
        "response": response,
        "forecast_id": forecast_id,
    }


@router.get("/chat/history")
def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user["user_id"])
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": m.id,
            "role": m.role,
            "message": m.message,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]
