-- SmartSales AI Database Schema
-- PostgreSQL

CREATE DATABASE smartsales;

\c smartsales;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    company VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded Files Table
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    file_size INTEGER,
    row_count INTEGER,
    column_names TEXT[],
    date_column VARCHAR(255),
    target_column VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Forecast Results Table
CREATE TABLE IF NOT EXISTS forecast_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    file_id INTEGER REFERENCES uploaded_files(id) ON DELETE CASCADE,
    model_type VARCHAR(50) NOT NULL,  -- 'prophet' or 'lightgbm'
    aggregation VARCHAR(20) NOT NULL, -- 'daily', 'weekly', 'monthly'
    horizon_months INTEGER NOT NULL,
    forecast_data JSONB NOT NULL,
    actual_data JSONB,
    projected_revenue FLOAT,
    growth_rate FLOAT,
    accuracy FLOAT,
    top_driver VARCHAR(255),
    confidence_lower JSONB,
    confidence_upper JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model Metrics Table
CREATE TABLE IF NOT EXISTS model_metrics (
    id SERIAL PRIMARY KEY,
    forecast_id INTEGER REFERENCES forecast_results(id) ON DELETE CASCADE,
    model_type VARCHAR(50) NOT NULL,
    mae FLOAT,
    rmse FLOAT,
    mape FLOAT,
    r2_score FLOAT,
    mean_error FLOAT,
    std_error FLOAT,
    residuals JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat History Table
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    forecast_id INTEGER REFERENCES forecast_results(id) ON DELETE SET NULL,
    role VARCHAR(20) NOT NULL,  -- 'user' or 'assistant'
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_uploaded_files_user ON uploaded_files(user_id);
CREATE INDEX idx_forecast_results_user ON forecast_results(user_id);
CREATE INDEX idx_forecast_results_file ON forecast_results(file_id);
CREATE INDEX idx_model_metrics_forecast ON model_metrics(forecast_id);
CREATE INDEX idx_chat_history_user ON chat_history(user_id);
CREATE INDEX idx_chat_history_forecast ON chat_history(forecast_id);
