from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), default="")
    company = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    files = relationship("UploadedFile", back_populates="user", cascade="all, delete")
    forecasts = relationship("ForecastResult", back_populates="user", cascade="all, delete")
    chats = relationship("ChatMessage", back_populates="user", cascade="all, delete")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer)
    row_count = Column(Integer)
    column_names = Column(JSON)
    date_column = Column(String(255))
    target_column = Column(String(255))
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="files")
    forecasts = relationship("ForecastResult", back_populates="file", cascade="all, delete")


class ForecastResult(Base):
    __tablename__ = "forecast_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(Integer, ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False)
    model_type = Column(String(50), nullable=False)
    aggregation = Column(String(20), nullable=False)
    horizon_months = Column(Integer, nullable=False)
    forecast_data = Column(JSON, nullable=False)
    actual_data = Column(JSON)
    projected_revenue = Column(Float)
    growth_rate = Column(Float)
    accuracy = Column(Float)
    top_driver = Column(String(255))
    confidence_lower = Column(JSON)
    confidence_upper = Column(JSON)
    decomposition = Column(JSON)
    currency_symbol = Column(String(10), default="₹")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="forecasts")
    file = relationship("UploadedFile", back_populates="forecasts")
    metrics = relationship("ModelMetric", back_populates="forecast", cascade="all, delete")
    chats = relationship("ChatMessage", back_populates="forecast")


class ModelMetric(Base):
    __tablename__ = "model_metrics"

    id = Column(Integer, primary_key=True, index=True)
    forecast_id = Column(
        Integer, ForeignKey("forecast_results.id", ondelete="CASCADE"), nullable=False
    )
    model_type = Column(String(50), nullable=False)
    mae = Column(Float)
    rmse = Column(Float)
    mape = Column(Float)
    r2_score = Column(Float)
    mean_error = Column(Float)
    std_error = Column(Float)
    residuals = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    forecast = relationship("ForecastResult", back_populates="metrics")


class ChatMessage(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    forecast_id = Column(
        Integer, ForeignKey("forecast_results.id", ondelete="SET NULL"), nullable=True
    )
    role = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chats")
    forecast = relationship("ForecastResult", back_populates="chats")
